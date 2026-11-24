"""
Router in front of the concrete spent DAO.

``SpentQuery`` inherits directly from the concrete ``SpentDAO`` for
whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``SpentService`` needs on top of them.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlmodel import col, func, or_, select

from app.dal.sql.spent_dao import SpentDAO
from app.db.sql.models.enums import Visibility
from app.db.sql.models.spent import Spent, SpentItem


class SpentQuery(SpentDAO):
    """Everything ``SpentService`` needs to read and write spent data."""

    async def list_for_range(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        category_id: int | None = None,
        account_id: uuid.UUID | None = None,
    ) -> list[Spent]:
        """
        Fetch spents visible to ``requester_id`` among ``owner_ids``.

        A row passes when its owner is ``requester_id`` (any visibility)
        or the owner is one of ``owner_ids`` and the row is
        ``Visibility.FAMILY`` -- narrowing to ``owner_ids`` alone would
        leak another family member's private spents into a family-scope
        list.

        :param requester_id: user asking for the list.
        :param owner_ids: owners whose spents are in scope (from
            :meth:`~app.services.visibility_service.VisibilityService.visible_owner_ids`).
        :param date_from: earliest ``spent_at`` to include, inclusive.
        :param date_to: latest ``spent_at`` to include, inclusive.
        :param category_id: restrict to one category.
        :param account_id: restrict to one account.
        :return: matching spents, most recent first.
        """
        query = (
            select(Spent)
            .where(col(Spent.user_id).in_(owner_ids))
            .where(
                or_(
                    Spent.user_id == requester_id,
                    Spent.visibility == Visibility.FAMILY,
                )
            )
        )
        if date_from is not None:
            query = query.where(col(Spent.spent_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Spent.spent_at) <= date_to)
        if category_id is not None:
            query = query.where(Spent.category_id == category_id)
        if account_id is not None:
            query = query.where(Spent.account_id == account_id)
        query = query.order_by(col(Spent.spent_at).desc())
        result = await self.session.exec(query)
        return list(result.all())

    async def list_realise_candidates(
        self, user_id: uuid.UUID, category_id: int, *, limit: int = 5
    ) -> list[Spent]:
        """
        Fetch spents a wishlist item could plausibly be realised against.

        Unlinked (not already tied to another wishlist item), same
        category, most recent first -- a ranking hint for the client's
        picker, not a correctness guarantee (see
        ``WishlistService.list_realise_candidates``).

        :param user_id: owner to look up.
        :param category_id: category to match.
        :param limit: maximum number of candidates to return.
        :return: candidate spents, most recent first.
        """
        query = (
            select(Spent)
            .where(Spent.user_id == user_id)
            .where(Spent.category_id == category_id)
            .where(col(Spent.wishlist_item_id).is_(None))
            .order_by(col(Spent.spent_at).desc())
            .limit(limit)
        )
        result = await self.session.exec(query)
        return list(result.all())

    async def list_bill_match_candidates(
        self,
        user_id: uuid.UUID,
        purchased_at: date,
        total_amount: Decimal,
        *,
        tolerance: Decimal,
    ) -> list[Spent]:
        """
        Fetch spents a market-bill import could plausibly attach items to.

        Same day, amount within ``tolerance``, and not already itemized
        -- a bill's items should never land on a spent that's already
        been split. ``ImportService.process_bill_import`` attaches only
        when this returns exactly one row; zero or multiple means "don't
        guess, create a new spent instead".

        :param user_id: owner to look up.
        :param purchased_at: the bill's purchase date.
        :param total_amount: the bill's parsed total.
        :param tolerance: how far a candidate's ``amount`` may differ
            from ``total_amount`` and still count as a match.
        :return: candidate spents.
        """
        already_itemized = select(SpentItem.spent_id).where(
            SpentItem.spent_id == Spent.id
        )
        query = (
            select(Spent)
            .where(Spent.user_id == user_id)
            .where(Spent.spent_at == purchased_at)
            .where(func.abs(Spent.amount - total_amount) <= tolerance)
            .where(~already_itemized.exists())
        )
        result = await self.session.exec(query)
        return list(result.all())

    async def sum_for_range(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Decimal:
        """
        Sum spents visible to ``requester_id`` among ``owner_ids``.

        Same visibility rule as :meth:`list_for_range`.

        :param requester_id: user asking for the total.
        :param owner_ids: owners whose spents are in scope.
        :param date_from: earliest ``spent_at`` to include, inclusive.
        :param date_to: latest ``spent_at`` to include, inclusive.
        :return: the total, ``0`` if nothing matched.
        """
        query = (
            select(func.coalesce(func.sum(Spent.amount), 0))
            .where(col(Spent.user_id).in_(owner_ids))
            .where(
                or_(
                    Spent.user_id == requester_id,
                    Spent.visibility == Visibility.FAMILY,
                )
            )
        )
        if date_from is not None:
            query = query.where(col(Spent.spent_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Spent.spent_at) <= date_to)
        result = await self.session.exec(query)
        return result.one()

    async def sum_by_category(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[int, Decimal]:
        """
        Sum spents visible to ``requester_id``, grouped by category.

        Same visibility rule as :meth:`list_for_range`.

        :param requester_id: user asking for the breakdown.
        :param owner_ids: owners whose spents are in scope.
        :param date_from: earliest ``spent_at`` to include, inclusive.
        :param date_to: latest ``spent_at`` to include, inclusive.
        :return: mapping of category id to total; categories with no
            matching spents are simply absent.
        """
        query = (
            select(Spent.category_id, func.sum(Spent.amount))
            .where(col(Spent.user_id).in_(owner_ids))
            .where(
                or_(
                    Spent.user_id == requester_id,
                    Spent.visibility == Visibility.FAMILY,
                )
            )
            .group_by(col(Spent.category_id))
        )
        if date_from is not None:
            query = query.where(col(Spent.spent_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Spent.spent_at) <= date_to)
        result = await self.session.exec(query)
        return dict(result.all())

    async def sum_by_account(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[uuid.UUID, Decimal]:
        """
        Sum spents visible to ``requester_id``, grouped by account.

        Same visibility rule as :meth:`list_for_range`.

        :param requester_id: user asking for the breakdown.
        :param owner_ids: owners whose spents are in scope.
        :param date_from: earliest ``spent_at`` to include, inclusive.
        :param date_to: latest ``spent_at`` to include, inclusive.
        :return: mapping of account id to total; accounts with no
            matching spents are simply absent.
        """
        query = (
            select(Spent.account_id, func.sum(Spent.amount))
            .where(col(Spent.user_id).in_(owner_ids))
            .where(
                or_(
                    Spent.user_id == requester_id,
                    Spent.visibility == Visibility.FAMILY,
                )
            )
            .group_by(col(Spent.account_id))
        )
        if date_from is not None:
            query = query.where(col(Spent.spent_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Spent.spent_at) <= date_to)
        result = await self.session.exec(query)
        return dict(result.all())

    async def sum_for_account(self, account_id: uuid.UUID) -> Decimal:
        """
        Sum every spent filed against one literal account.

        :param account_id: account to total.
        :return: the total, ``0`` if there are none.
        """
        query = select(func.coalesce(func.sum(Spent.amount), 0)).where(
            Spent.account_id == account_id
        )
        return (await self.session.exec(query)).one()

    async def list_for_dedupe(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
        account_id: uuid.UUID | None = None,
    ) -> list[Spent]:
        """
        Fetch a user's own spents in a date range, for statement dedupe.

        :param user_id: owner.
        :param date_from: earliest ``spent_at``, inclusive.
        :param date_to: latest ``spent_at``, inclusive.
        :param account_id: restrict to one account, if given.
        :return: matching spents, any visibility.
        """
        query = (
            select(Spent)
            .where(Spent.user_id == user_id)
            .where(col(Spent.spent_at) >= date_from)
            .where(col(Spent.spent_at) <= date_to)
        )
        if account_id is not None:
            query = query.where(Spent.account_id == account_id)
        result = await self.session.exec(query)
        return list(result.all())
