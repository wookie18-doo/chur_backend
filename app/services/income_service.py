import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.account_query import AccountQuery
from app.dal.income_query import IncomeQuery
from app.db.sql.models.enums import Visibility
from app.db.sql.models.income import Income
from app.db.sql.models.users import User
from app.services.visibility_service import VisibilityService


class IncomeNotFoundError(Exception):
    """Raised when an income isn't visible/owned."""


class InvalidAccountError(Exception):
    """Raised when an income is filed against an account the actor doesn't own."""


class IncomeService:
    """
    Business logic for logging and browsing real income.

    Builds its own :class:`~app.dal.income_query.IncomeQuery` and
    :class:`~app.dal.account_query.AccountQuery` from the db session it's
    given -- callers never construct a query object themselves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.incomes = IncomeQuery(session)
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
        received_at: date,
        description: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
        planned_income_id: uuid.UUID | None = None,
        recurring_occurrence_id: uuid.UUID | None = None,
    ) -> Income:
        """
        Log a new income for ``actor``.

        :param actor: the income's owner.
        :param account_id: account it was paid into -- must belong to ``actor``.
        :param category_id: category to file it under.
        :param amount: amount received.
        :param received_at: date it happened.
        :param description: free-text note.
        :param visibility: who besides ``actor`` may see it.
        :param planned_income_id: the planned income this realises, if
            any (set by ``PlannedIncomeService.realise``'s
            create-a-new-income path).
        :param recurring_occurrence_id: the recurring occurrence this record
            confirms, if any (set by ``RecurringTransactionService``).
        :raises InvalidAccountError: if ``account_id`` isn't ``actor``'s.
        :return: the created income.
        """
        await self._check_account(actor, account_id)
        return await self.incomes.create(
            user_id=actor.id,
            account_id=account_id,
            category_id=category_id,
            amount=amount,
            received_at=received_at,
            description=description,
            recurring_occurrence_id=recurring_occurrence_id,
            visibility=visibility,
            planned_income_id=planned_income_id,
        )

    async def _get_owned(self, actor: User, income_id: uuid.UUID) -> Income:
        income = await self.incomes.get(income_id)
        if income is None or income.user_id != actor.id:
            raise IncomeNotFoundError
        return income

    async def get_visible(self, actor: User, income_id: uuid.UUID) -> Income:
        """
        Fetch an income ``actor`` is allowed to read.

        :param actor: user requesting the income.
        :param income_id: income to fetch.
        :raises IncomeNotFoundError: if it doesn't exist or isn't visible
            to ``actor``.
        :return: the income.
        """
        income = await self.incomes.get(income_id)
        if income is None:
            raise IncomeNotFoundError
        visibility_service = VisibilityService(actor.id, self.session)
        if not await visibility_service.can_view(income.user_id, income.visibility):
            raise IncomeNotFoundError
        return income

    async def update(
        self, actor: User, income_id: uuid.UUID, **fields: object
    ) -> Income:
        """
        Update fields on an income owned by ``actor``.

        :param actor: user requesting the update.
        :param income_id: income to update.
        :param fields: field values to set.
        :raises IncomeNotFoundError: if it isn't owned by ``actor``.
        :raises InvalidAccountError: if ``account_id`` is being changed
            to one that isn't ``actor``'s.
        :return: the updated income.
        """
        await self._get_owned(actor, income_id)
        if "account_id" in fields:
            await self._check_account(actor, cast(uuid.UUID, fields["account_id"]))
        return cast(Income, await self.incomes.update(income_id, **fields))

    async def delete(self, actor: User, income_id: uuid.UUID) -> None:
        """
        Delete an income owned by ``actor``.

        :param actor: user requesting the deletion.
        :param income_id: income to delete.
        :raises IncomeNotFoundError: if it isn't owned by ``actor``.
        """
        await self._get_owned(actor, income_id)
        await self.incomes.delete(income_id)

    async def list_realise_candidates(
        self, actor: User, category_id: int
    ) -> list[Income]:
        """
        Suggest incomes a planned income could plausibly be realised against.

        :param actor: user the candidates must belong to.
        :param category_id: category to match.
        :return: candidate incomes, most recent first.
        """
        return await self.incomes.list_realise_candidates(actor.id, category_id)

    async def list_incomes(
        self,
        actor: User,
        *,
        scope: str = "me",
        date_from: date | None = None,
        date_to: date | None = None,
        category_id: int | None = None,
        account_id: uuid.UUID | None = None,
    ) -> list[Income]:
        """
        List incomes visible to ``actor``.

        :param actor: user requesting the list.
        :param scope: ``"me"`` or ``"family"``.
        :param date_from: earliest ``received_at`` to include, inclusive.
        :param date_to: latest ``received_at`` to include, inclusive.
        :param category_id: restrict to one category.
        :param account_id: restrict to one account.
        :return: matching incomes, most recent first.
        """
        visibility_service = VisibilityService(actor.id, self.session)
        owner_ids = await visibility_service.visible_owner_ids(scope=scope)
        return await self.incomes.list_for_range(
            actor.id,
            owner_ids,
            date_from=date_from,
            date_to=date_to,
            category_id=category_id,
            account_id=account_id,
        )
