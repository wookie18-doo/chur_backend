import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.account_query import AccountQuery
from app.dal.wishlist_item_query import WishlistItemQuery
from app.dal.wishlist_query import WishlistQuery
from app.db.sql.models.enums import PlanStatus, RecurrenceFrequency, Visibility
from app.db.sql.models.spent import Spent
from app.db.sql.models.users import User
from app.db.sql.models.wishlist import Wishlist, WishlistItem
from app.services.plan_repeat import check_repeat, next_window
from app.services.spent_service import SpentNotFoundError, SpentService
from app.services.visibility_service import VisibilityService


class WishlistNotFoundError(Exception):
    """Raised when a wishlist (or one of its items) isn't visible/owned."""


class InvalidTargetWishlistError(Exception):
    """Raised when transferring an item to a wishlist the actor doesn't own."""


class InvalidSpentError(Exception):
    """Raised when realising against a spent the actor doesn't own."""


class InvalidAccountError(Exception):
    """Raised when a plan names an account the actor doesn't own."""


class MissingAccountError(Exception):
    """Raised when realising into a new spent without naming an account."""


class WishlistService:
    """
    Business logic for planning future spending.

    Builds its own :class:`~app.dal.wishlist_query.WishlistQuery` and
    :class:`~app.dal.wishlist_item_query.WishlistItemQuery` from the db
    session it's given, and reuses :class:`~app.services.spent_service.
    SpentService` for creating/linking the spents a wishlist item
    realises into -- callers never construct a query object themselves,
    and realisation logic isn't duplicated.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.wishlists = WishlistQuery(session)
        self.items = WishlistItemQuery(session)
        self.spent_service = SpentService(session)
        self.account_queries = AccountQuery(session)

    async def _check_account(self, actor: User, account_id: uuid.UUID) -> None:
        account = await self.account_queries.get(account_id)
        if account is None or account.user_id != actor.id:
            raise InvalidAccountError

    async def create_wishlist(
        self,
        actor: User,
        name: str,
        *,
        description: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        visibility: Visibility = Visibility.PRIVATE,
    ) -> Wishlist:
        """
        Create a wishlist owned by ``actor``.

        :param actor: the wishlist's owner.
        :param name: wishlist name.
        :param description: free-text note.
        :param date_from: optional start of the planning period.
        :param date_to: optional end of the planning period.
        :param visibility: default visibility for items that don't
            override it.
        :return: the created wishlist.
        """
        return await self.wishlists.create(
            user_id=actor.id,
            name=name,
            description=description,
            date_from=date_from,
            date_to=date_to,
            visibility=visibility,
        )

    async def _get_owned_wishlist(
        self, actor: User, wishlist_id: uuid.UUID
    ) -> Wishlist:
        wishlist = await self.wishlists.get(wishlist_id)
        if wishlist is None or wishlist.user_id != actor.id:
            raise WishlistNotFoundError
        return wishlist

    async def get_visible(self, actor: User, wishlist_id: uuid.UUID) -> Wishlist:
        """
        Fetch a wishlist ``actor`` is allowed to read.

        :param actor: user requesting the wishlist.
        :param wishlist_id: wishlist to fetch.
        :raises WishlistNotFoundError: if it doesn't exist or isn't
            visible to ``actor``.
        :return: the wishlist.
        """
        wishlist = await self.wishlists.get(wishlist_id)
        if wishlist is None:
            raise WishlistNotFoundError
        visibility_service = VisibilityService(actor.id, self.session)
        if not await visibility_service.can_view(wishlist.user_id, wishlist.visibility):
            raise WishlistNotFoundError
        return wishlist

    async def list_items(
        self, actor: User, wishlist_id: uuid.UUID
    ) -> list[WishlistItem]:
        """
        List a wishlist's items, for anyone allowed to read the wishlist.

        The wishlist's own visibility only gates whether ``actor`` sees
        *any* items at all. Each item's own visibility can still narrow
        that further -- an item overridden to ``PRIVATE`` on an
        otherwise ``FAMILY`` wishlist (the mockup's "hidden from family"
        item) must stay invisible to a family member even though they
        can see the wishlist itself; the owner always sees every item
        regardless.

        :param actor: user requesting the list.
        :param wishlist_id: parent wishlist.
        :raises WishlistNotFoundError: if the wishlist isn't visible to
            ``actor``.
        :return: its items, filtered to what ``actor`` may individually see.
        """
        wishlist = await self.get_visible(actor, wishlist_id)
        items = await self.items.list_by_wishlist(wishlist.id)
        if actor.id == wishlist.user_id:
            return items
        return [
            item
            for item in items
            if (item.visibility or wishlist.visibility) == Visibility.FAMILY
        ]

    async def update_wishlist(
        self, actor: User, wishlist_id: uuid.UUID, **fields: object
    ) -> Wishlist:
        """
        Update fields on a wishlist owned by ``actor``.

        :param actor: user requesting the update.
        :param wishlist_id: wishlist to update.
        :param fields: field values to set.
        :raises WishlistNotFoundError: if it isn't owned by ``actor``.
        :return: the updated wishlist.
        """
        await self._get_owned_wishlist(actor, wishlist_id)
        return cast(Wishlist, await self.wishlists.update(wishlist_id, **fields))

    async def delete_wishlist(self, actor: User, wishlist_id: uuid.UUID) -> None:
        """
        Delete a wishlist owned by ``actor``, and its items (cascade).

        :param actor: user requesting the deletion.
        :param wishlist_id: wishlist to delete.
        :raises WishlistNotFoundError: if it isn't owned by ``actor``.
        """
        await self._get_owned_wishlist(actor, wishlist_id)
        await self.wishlists.delete(wishlist_id)

    async def list_wishlists(self, actor: User, *, scope: str = "me") -> list[Wishlist]:
        """
        List wishlists visible to ``actor``.

        :param actor: user requesting the list.
        :param scope: ``"me"`` or ``"family"``.
        :return: matching wishlists.
        """
        visibility_service = VisibilityService(actor.id, self.session)
        owner_ids = await visibility_service.visible_owner_ids(scope=scope)
        return await self.wishlists.list_visible(actor.id, owner_ids)

    async def add_item(
        self,
        actor: User,
        wishlist_id: uuid.UUID,
        *,
        category_id: int,
        name: str,
        amount: Decimal,
        planned_date: date | None = None,
        planned_date_to: date | None = None,
        frequency: RecurrenceFrequency | None = None,
        repeat_until: date | None = None,
        visibility: Visibility | None = None,
        account_id: uuid.UUID | None = None,
    ) -> WishlistItem:
        """
        Add a planned item to a wishlist owned by ``actor``.

        :param actor: user requesting the change.
        :param wishlist_id: parent wishlist.
        :param category_id: category to file it under.
        :param name: item name.
        :param amount: planned amount.
        :param planned_date: when the purchase is expected, if known.
        :param planned_date_to: end of the expected window, if any.
        :param frequency: repeat period; realising rolls the window forward.
        :param repeat_until: last date a repeat may start on, if any.
        :param visibility: override the wishlist's own default, if set.
        :param account_id: account the purchase is planned against, if known.
        :raises WishlistNotFoundError: if the wishlist isn't owned by ``actor``.
        :raises InvalidAccountError: if ``account_id`` isn't ``actor``'s.
        :raises InvalidRepeatError: if ``frequency`` is set without ``planned_date``.
        :return: the created item.
        """
        await self._get_owned_wishlist(actor, wishlist_id)
        anchor_day = check_repeat(frequency, planned_date)
        if account_id is not None:
            await self._check_account(actor, account_id)
        return await self.items.create(
            wishlist_id=wishlist_id,
            category_id=category_id,
            name=name,
            amount=amount,
            planned_date=planned_date,
            planned_date_to=planned_date_to,
            frequency=frequency,
            repeat_until=repeat_until,
            repeat_anchor_day=anchor_day,
            visibility=visibility,
            account_id=account_id,
        )

    async def _get_owned_item(self, actor: User, item_id: uuid.UUID) -> WishlistItem:
        item = await self.items.get(item_id)
        if item is None:
            raise WishlistNotFoundError
        await self._get_owned_wishlist(actor, item.wishlist_id)
        return item

    async def update_item(
        self, actor: User, item_id: uuid.UUID, **fields: object
    ) -> WishlistItem:
        """
        Update a planned item on a wishlist owned by ``actor``.

        :param actor: user requesting the update.
        :param item_id: item to update.
        :param fields: field values to set.
        :raises WishlistNotFoundError: if it doesn't exist or its wishlist
            isn't owned by ``actor``.
        :raises InvalidAccountError: if ``account_id`` isn't ``actor``'s.
        :raises InvalidRepeatError: if the item would repeat without a date.
        :return: the updated item.
        """
        item = await self._get_owned_item(actor, item_id)
        if fields.get("account_id") is not None:
            await self._check_account(actor, cast(uuid.UUID, fields["account_id"]))
        if fields.keys() & {"frequency", "planned_date"}:
            fields["repeat_anchor_day"] = check_repeat(
                cast(
                    RecurrenceFrequency | None,
                    fields.get("frequency", item.frequency),
                ),
                cast(date | None, fields.get("planned_date", item.planned_date)),
            )
        return cast(WishlistItem, await self.items.update(item_id, **fields))

    async def delete_item(self, actor: User, item_id: uuid.UUID) -> None:
        """
        Delete a planned item from a wishlist owned by ``actor``.

        :param actor: user requesting the deletion.
        :param item_id: item to delete.
        :raises WishlistNotFoundError: if it doesn't exist or its wishlist
            isn't owned by ``actor``.
        """
        await self._get_owned_item(actor, item_id)
        await self.items.delete(item_id)

    async def transfer_item(
        self, actor: User, item_id: uuid.UUID, target_wishlist_id: uuid.UUID
    ) -> WishlistItem:
        """
        Move a planned item to another wishlist ``actor`` owns.

        ``status`` is untouched -- a transfer is an event (the item's
        ``wishlist_id`` changing), not a resting state.

        :param actor: user requesting the transfer.
        :param item_id: item to move.
        :param target_wishlist_id: wishlist to move it to.
        :raises WishlistNotFoundError: if the item's current wishlist
            isn't owned by ``actor``.
        :raises InvalidTargetWishlistError: if ``target_wishlist_id``
            isn't owned by ``actor``.
        :return: the updated item.
        """
        await self._get_owned_item(actor, item_id)
        try:
            await self._get_owned_wishlist(actor, target_wishlist_id)
        except WishlistNotFoundError as exc:
            raise InvalidTargetWishlistError from exc
        return cast(
            WishlistItem,
            await self.items.update(item_id, wishlist_id=target_wishlist_id),
        )

    async def list_realise_candidates(
        self, actor: User, item_id: uuid.UUID
    ) -> list[Spent]:
        """
        Suggest existing spents an item could be realised against.

        :param actor: user requesting the candidates.
        :param item_id: item to suggest candidates for.
        :raises WishlistNotFoundError: if it doesn't exist or its wishlist
            isn't owned by ``actor``.
        :return: candidate spents, most recent first.
        """
        item = await self._get_owned_item(actor, item_id)
        return await self.spent_service.list_realise_candidates(actor, item.category_id)

    async def _effective_visibility(self, item: WishlistItem) -> Visibility:
        if item.visibility is not None:
            return item.visibility
        wishlist = cast(Wishlist, await self.wishlists.get(item.wishlist_id))
        return wishlist.visibility

    async def realise_item(
        self,
        actor: User,
        item_id: uuid.UUID,
        *,
        existing_spent_id: uuid.UUID | None = None,
        spent_overrides: dict[str, Any] | None = None,
    ) -> WishlistItem:
        """
        Mark a planned item as bought, linking it to a real spent.

        Two paths: merge into a spent that's already recorded, or create
        a brand-new one from the item's own fields.

        :param actor: user requesting the realisation.
        :param item_id: item being realised.
        :param existing_spent_id: an existing spent owned by ``actor`` to
            link instead of creating a new one -- typically one of
            :meth:`list_realise_candidates`'s results, though any spent
            id the caller already knows works too.
        :param spent_overrides: for the create-a-new-spent path only;
            ``account_id`` falls back to the item's own planned account
            and is **required** if neither is set. ``category_id``/``amount``/
            ``spent_at``/``visibility`` fall back to the item's own values if omitted.
        :raises WishlistNotFoundError: if the item's wishlist isn't
            owned by ``actor``.
        :raises InvalidSpentError: if ``existing_spent_id`` isn't owned
            by ``actor``.
        :raises MissingAccountError: if creating a new spent without an
            ``account_id`` override and the item has none planned.
        :return: the realised item; a repeating item stays ``PLANNED`` and
            moves to its next window instead, unless ``repeat_until`` is passed.
        """
        item = await self._get_owned_item(actor, item_id)

        if existing_spent_id is not None:
            try:
                spent = await self.spent_service.update(
                    actor, existing_spent_id, wishlist_item_id=item.id
                )
            except SpentNotFoundError as exc:
                raise InvalidSpentError from exc
        else:
            overrides = dict(spent_overrides or {})
            account_id = overrides.get("account_id") or item.account_id
            if account_id is None:
                raise MissingAccountError
            spent = await self.spent_service.create(
                actor,
                account_id=account_id,
                category_id=overrides.get("category_id", item.category_id),
                amount=overrides.get("amount", item.amount),
                spent_at=overrides.get("spent_at", item.planned_date or date.today()),
                visibility=overrides.get(
                    "visibility", await self._effective_visibility(item)
                ),
                wishlist_item_id=item.id,
            )

        changes: dict[str, Any] = {
            "status": PlanStatus.REALISED,
            "realised_spent_id": spent.id,
        }
        if item.frequency is not None and item.planned_date is not None:
            start, end = next_window(
                item.frequency,
                item.repeat_anchor_day,
                item.planned_date,
                item.planned_date_to,
            )
            if item.repeat_until is None or start <= item.repeat_until:
                changes.update(
                    status=PlanStatus.PLANNED, planned_date=start, planned_date_to=end
                )
        return cast(WishlistItem, await self.items.update(item.id, **changes))
