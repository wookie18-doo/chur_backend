"""
Router in front of the concrete income DAO.

``IncomeQuery`` inherits directly from the concrete ``IncomeDAO`` for
whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``IncomeService`` needs on top of them.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlmodel import col, func, or_, select

from app.dal.sql.income_dao import IncomeDAO
from app.db.sql.models.enums import Visibility
from app.db.sql.models.income import Income


class IncomeQuery(IncomeDAO):
    """Everything ``IncomeService`` needs to read and write income data."""

    async def list_for_range(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        category_id: int | None = None,
        account_id: uuid.UUID | None = None,
    ) -> list[Income]:
        """
        Fetch incomes visible to ``requester_id`` among ``owner_ids``.

        Same visibility rule as ``SpentQuery.list_for_range``: a row
        passes when its owner is ``requester_id`` (any visibility) or
        the owner is one of ``owner_ids`` and the row is
        ``Visibility.FAMILY``.

        :param requester_id: user asking for the list.
        :param owner_ids: owners whose incomes are in scope.
        :param date_from: earliest ``received_at`` to include, inclusive.
        :param date_to: latest ``received_at`` to include, inclusive.
        :param category_id: restrict to one category.
        :param account_id: restrict to one account.
        :return: matching incomes, most recent first.
        """
        query = (
            select(Income)
            .where(col(Income.user_id).in_(owner_ids))
            .where(
                or_(
                    Income.user_id == requester_id,
                    Income.visibility == Visibility.FAMILY,
                )
            )
        )
        if date_from is not None:
            query = query.where(col(Income.received_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Income.received_at) <= date_to)
        if category_id is not None:
            query = query.where(Income.category_id == category_id)
        if account_id is not None:
            query = query.where(Income.account_id == account_id)
        query = query.order_by(col(Income.received_at).desc())
        result = await self.session.exec(query)
        return list(result.all())

    async def list_realise_candidates(
        self, user_id: uuid.UUID, category_id: int, *, limit: int = 5
    ) -> list[Income]:
        """
        Fetch incomes a planned income could plausibly be realised against.

        Unlinked (not already claimed by another planned income), most
        recent first -- a ranking hint for the client's picker, not a
        correctness guarantee, mirroring
        ``SpentQuery.list_realise_candidates``.

        :param user_id: owner to look up.
        :param category_id: category to match.
        :param limit: maximum number of candidates to return.
        :return: candidate incomes, most recent first.
        """
        query = (
            select(Income)
            .where(Income.user_id == user_id)
            .where(Income.category_id == category_id)
            .where(col(Income.planned_income_id).is_(None))
            .order_by(col(Income.received_at).desc())
            .limit(limit)
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
        Sum incomes visible to ``requester_id`` among ``owner_ids``.

        Same visibility rule as :meth:`list_for_range`.

        :param requester_id: user asking for the total.
        :param owner_ids: owners whose incomes are in scope.
        :param date_from: earliest ``received_at`` to include, inclusive.
        :param date_to: latest ``received_at`` to include, inclusive.
        :return: the total, ``0`` if nothing matched.
        """
        query = (
            select(func.coalesce(func.sum(Income.amount), 0))
            .where(col(Income.user_id).in_(owner_ids))
            .where(
                or_(
                    Income.user_id == requester_id,
                    Income.visibility == Visibility.FAMILY,
                )
            )
        )
        if date_from is not None:
            query = query.where(col(Income.received_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Income.received_at) <= date_to)
        result = await self.session.exec(query)
        return result.one()

    async def sum_by_account(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[uuid.UUID, Decimal]:
        """
        Sum incomes visible to ``requester_id``, grouped by account.

        Same visibility rule as :meth:`list_for_range`.

        :param requester_id: user asking for the breakdown.
        :param owner_ids: owners whose incomes are in scope.
        :param date_from: earliest ``received_at`` to include, inclusive.
        :param date_to: latest ``received_at`` to include, inclusive.
        :return: mapping of account id to total; accounts with no
            matching incomes are simply absent.
        """
        query = (
            select(Income.account_id, func.sum(Income.amount))
            .where(col(Income.user_id).in_(owner_ids))
            .where(
                or_(
                    Income.user_id == requester_id,
                    Income.visibility == Visibility.FAMILY,
                )
            )
            .group_by(col(Income.account_id))
        )
        if date_from is not None:
            query = query.where(col(Income.received_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Income.received_at) <= date_to)
        result = await self.session.exec(query)
        return dict(result.all())

    async def sum_for_account(self, account_id: uuid.UUID) -> Decimal:
        """
        Sum every income filed against one literal account.

        :param account_id: account to total.
        :return: the total, ``0`` if there are none.
        """
        query = select(func.coalesce(func.sum(Income.amount), 0)).where(
            Income.account_id == account_id
        )
        return (await self.session.exec(query)).one()

    async def list_for_dedupe(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
        account_id: uuid.UUID | None = None,
    ) -> list[Income]:
        """
        Fetch a user's own incomes in a date range, for statement dedupe.

        :param user_id: owner.
        :param date_from: earliest ``received_at``, inclusive.
        :param date_to: latest ``received_at``, inclusive.
        :param account_id: restrict to one account, if given.
        :return: matching incomes, any visibility.
        """
        query = (
            select(Income)
            .where(Income.user_id == user_id)
            .where(col(Income.received_at) >= date_from)
            .where(col(Income.received_at) <= date_to)
        )
        if account_id is not None:
            query = query.where(Income.account_id == account_id)
        result = await self.session.exec(query)
        return list(result.all())
