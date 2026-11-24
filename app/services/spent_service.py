import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.account_query import AccountQuery
from app.dal.spent_item_query import SpentItemQuery
from app.dal.spent_query import SpentQuery
from app.db.sql.models.enums import Visibility
from app.db.sql.models.spent import Spent, SpentItem
from app.db.sql.models.users import User
from app.services.visibility_service import VisibilityService


class SpentNotFoundError(Exception):
    """Raised when a spent (or one of its line items) isn't visible/owned."""


class InvalidAccountError(Exception):
    """Raised when a spent is filed against an account the actor doesn't own."""


class SpentService:
    """
    Business logic for logging and browsing real expenses.

    Builds its own :class:`~app.dal.spent_query.SpentQuery`,
    :class:`~app.dal.spent_item_query.SpentItemQuery`, and
    :class:`~app.dal.account_query.AccountQuery` from the db session it's
    given -- callers never construct a query object themselves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.spents = SpentQuery(session)
        self.items = SpentItemQuery(session)
        self.account_queries = AccountQuery(session)

    async def _check_account(self, actor: User, account_id: uuid.UUID) -> None:
        account = await self.account_queries.get(account_id)
        if account is None or account.user_id != actor.id:
            raise InvalidAccountError

    async def create(
        self,
        actor: User,
        *,
        account_id: uuid.UUID,
        category_id: int,
        amount: Decimal,
        spent_at: date,
        description: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
        wishlist_item_id: uuid.UUID | None = None,
        recurring_occurrence_id: uuid.UUID | None = None,
    ) -> Spent:
        """
        Log a new spent for ``actor``.

        :param actor: the spent's owner.
        :param account_id: account it was paid from -- must belong to ``actor``.
        :param category_id: category to file it under.
        :param amount: amount spent.
        :param spent_at: date it happened.
        :param description: free-text note.
        :param visibility: who besides ``actor`` may see it.
        :param wishlist_item_id: the wishlist item this spent realises,
            if any (set by ``WishlistService.realise_item``'s
            create-a-new-spent path -- not part of manual entry).
        :param recurring_occurrence_id: the recurring occurrence this record
            confirms, if any (set by ``RecurringTransactionService``).
        :raises InvalidAccountError: if ``account_id`` isn't ``actor``'s.
        :return: the created spent.
        """
        await self._check_account(actor, account_id)
        return await self.spents.create(
            user_id=actor.id,
            account_id=account_id,
            category_id=category_id,
            amount=amount,
            spent_at=spent_at,
            description=description,
            recurring_occurrence_id=recurring_occurrence_id,
            visibility=visibility,
            wishlist_item_id=wishlist_item_id,
        )

    async def _get_owned(self, actor: User, spent_id: uuid.UUID) -> Spent:
        spent = await self.spents.get(spent_id)
        if spent is None or spent.user_id != actor.id:
            raise SpentNotFoundError
        return spent

    async def get_visible(self, actor: User, spent_id: uuid.UUID) -> Spent:
        """
        Fetch a spent ``actor`` is allowed to read.

        :param actor: user requesting the spent.
        :param spent_id: spent to fetch.
        :raises SpentNotFoundError: if it doesn't exist or isn't visible
            to ``actor`` (never distinguished from "doesn't exist").
        :return: the spent.
        """
        spent = await self.spents.get(spent_id)
        if spent is None:
            raise SpentNotFoundError
        visibility_service = VisibilityService(actor.id, self.session)
        if not await visibility_service.can_view(spent.user_id, spent.visibility):
            raise SpentNotFoundError
        return spent

    async def update(self, actor: User, spent_id: uuid.UUID, **fields: object) -> Spent:
        """
        Update fields on a spent owned by ``actor``.

        :param actor: user requesting the update.
        :param spent_id: spent to update.
        :param fields: field values to set.
        :raises SpentNotFoundError: if it isn't owned by ``actor``.
        :raises InvalidAccountError: if ``account_id`` is being changed
            to one that isn't ``actor``'s.
        :return: the updated spent.
        """
        await self._get_owned(actor, spent_id)
        if "account_id" in fields:
            await self._check_account(actor, cast(uuid.UUID, fields["account_id"]))
        return cast(Spent, await self.spents.update(spent_id, **fields))

    async def delete(self, actor: User, spent_id: uuid.UUID) -> None:
        """
        Delete a spent owned by ``actor``.

        :param actor: user requesting the deletion.
        :param spent_id: spent to delete.
        :raises SpentNotFoundError: if it isn't owned by ``actor``.
        """
        await self._get_owned(actor, spent_id)
        await self.spents.delete(spent_id)

    async def list_spents(
        self,
        actor: User,
        *,
        scope: str = "me",
        date_from: date | None = None,
        date_to: date | None = None,
        category_id: int | None = None,
        account_id: uuid.UUID | None = None,
    ) -> list[Spent]:
        """
        List spents visible to ``actor``.

        :param actor: user requesting the list.
        :param scope: ``"me"`` or ``"family"``.
        :param date_from: earliest ``spent_at`` to include, inclusive.
        :param date_to: latest ``spent_at`` to include, inclusive.
        :param category_id: restrict to one category.
        :param account_id: restrict to one account.
        :return: matching spents, most recent first.
        """
        visibility_service = VisibilityService(actor.id, self.session)
        owner_ids = await visibility_service.visible_owner_ids(scope=scope)
        return await self.spents.list_for_range(
            actor.id,
            owner_ids,
            date_from=date_from,
            date_to=date_to,
            category_id=category_id,
            account_id=account_id,
        )

    async def list_realise_candidates(
        self, actor: User, category_id: int
    ) -> list[Spent]:
        """
        Suggest spents a wishlist item could plausibly be realised against.

        A ranking hint for :class:`~app.services.wishlist_service.WishlistService`'s
        match-candidates picker, not a correctness guarantee -- see
        ``SpentQuery.list_realise_candidates``.

        :param actor: user the candidates must belong to.
        :param category_id: category to match.
        :return: candidate spents, most recent first.
        """
        return await self.spents.list_realise_candidates(actor.id, category_id)

    async def add_item(
        self,
        actor: User,
        spent_id: uuid.UUID,
        *,
        name: str,
        amount: Decimal,
        category_id: int | None = None,
        quantity: str | None = None,
    ) -> SpentItem:
        """
        Attach a line item to a spent owned by ``actor``.

        :param actor: user requesting the change.
        :param spent_id: parent spent.
        :param name: line item name.
        :param amount: line item price.
        :param category_id: override category, if different from the
            parent spent's own.
        :param quantity: freeform display text (e.g. "x2", "1.2 kg").
        :raises SpentNotFoundError: if the spent isn't owned by ``actor``.
        :return: the created line item.
        """
        await self._get_owned(actor, spent_id)
        return await self.items.create(
            spent_id=spent_id,
            name=name,
            amount=amount,
            category_id=category_id,
            quantity=quantity,
        )

    async def _get_owned_item(self, actor: User, item_id: uuid.UUID) -> SpentItem:
        item = await self.items.get(item_id)
        if item is None:
            raise SpentNotFoundError
        await self._get_owned(actor, item.spent_id)
        return item

    async def update_item(
        self, actor: User, item_id: uuid.UUID, **fields: object
    ) -> SpentItem:
        """
        Update a line item belonging to a spent owned by ``actor``.

        :param actor: user requesting the update.
        :param item_id: line item to update.
        :param fields: field values to set.
        :raises SpentNotFoundError: if it doesn't exist or its parent
            spent isn't owned by ``actor``.
        :return: the updated line item.
        """
        await self._get_owned_item(actor, item_id)
        return cast(SpentItem, await self.items.update(item_id, **fields))

    async def delete_item(self, actor: User, item_id: uuid.UUID) -> None:
        """
        Delete a line item belonging to a spent owned by ``actor``.

        :param actor: user requesting the deletion.
        :param item_id: line item to delete.
        :raises SpentNotFoundError: if it doesn't exist or its parent
            spent isn't owned by ``actor``.
        """
        await self._get_owned_item(actor, item_id)
        await self.items.delete(item_id)

    async def list_items(self, actor: User, spent_id: uuid.UUID) -> list[SpentItem]:
        """
        List a spent's line items, for anyone allowed to read the spent.

        :param actor: user requesting the list.
        :param spent_id: parent spent.
        :raises SpentNotFoundError: if the spent isn't visible to ``actor``.
        :return: its line items.
        """
        spent = await self.get_visible(actor, spent_id)
        return await self.items.list_by_spent(spent.id)

    async def item_counts(self, spent_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """
        Count line items per spent, for a batch of spents at once.

        :param spent_ids: spents to count items for.
        :return: mapping of spent id to its item count; spents with no
            items are absent, not mapped to ``0``.
        """
        return await self.items.count_by_spents(spent_ids)

    async def items_total(self, spent_id: uuid.UUID) -> Decimal | None:
        """
        Sum a spent's line items.

        :param spent_id: parent spent.
        :return: the total, or ``None`` if it has no line items yet.
        """
        return await self.items.sum_by_spent(spent_id)
