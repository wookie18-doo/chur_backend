import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.account_query import AccountQuery
from app.dal.planned_income_query import PlannedIncomeQuery
from app.db.sql.models.enums import PlanStatus, RecurrenceFrequency, Visibility
from app.db.sql.models.income import Income
from app.db.sql.models.planned_income import PlannedIncome
from app.db.sql.models.users import User
from app.services.income_service import IncomeNotFoundError, IncomeService
from app.services.plan_repeat import check_repeat, next_window
from app.services.visibility_service import VisibilityService


class PlannedIncomeNotFoundError(Exception):
    """Raised when a planned income isn't visible/owned."""


class InvalidIncomeError(Exception):
    """Raised when realising against an income the actor doesn't own."""


class InvalidAccountError(Exception):
    """Raised when a plan names an account the actor doesn't own."""


class MissingAccountError(Exception):
    """Raised when realising into a new income without naming an account."""


class PlannedIncomeService:
    """
    Business logic for planning future income.

    Flat, unlike ``WishlistService`` -- no container list, just the item
    lifecycle. Builds its own :class:`~app.dal.planned_income_query.
    PlannedIncomeQuery` from the db session it's given, and reuses
    :class:`~app.services.income_service.IncomeService` for creating/
    linking the incomes a planned income realises into -- callers never
    construct a query object themselves, and realisation logic isn't
    duplicated.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.planned_incomes = PlannedIncomeQuery(session)
        self.income_service = IncomeService(session)
        self.account_queries = AccountQuery(session)

    async def _check_account(self, actor: User, account_id: uuid.UUID) -> None:
        account = await self.account_queries.get(account_id)
        if account is None or account.user_id != actor.id:
            raise InvalidAccountError

    async def create(
        self,
        actor: User,
        name: str,
        category_id: int,
        amount: Decimal,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        frequency: RecurrenceFrequency | None = None,
        repeat_until: date | None = None,
        visibility: Visibility = Visibility.PRIVATE,
        account_id: uuid.UUID | None = None,
    ) -> PlannedIncome:
        """
        Create a planned income owned by ``actor``.

        :param actor: the planned income's owner.
        :param name: name.
        :param category_id: category to file it under.
        :param amount: expected amount.
        :param date_from: optional start of the expected window.
        :param date_to: optional end of the expected window.
        :param frequency: repeat period; realising rolls the window forward.
        :param repeat_until: last date a repeat may start on, if any.
        :param visibility: who besides ``actor`` may see it.
        :param account_id: account the income is expected into, if known.
        :raises InvalidAccountError: if ``account_id`` isn't ``actor``'s.
        :raises InvalidRepeatError: if ``frequency`` is set without ``date_from``.
        :return: the created planned income.
        """
        anchor_day = check_repeat(frequency, date_from)
        if account_id is not None:
            await self._check_account(actor, account_id)
        return await self.planned_incomes.create(
            user_id=actor.id,
            name=name,
            category_id=category_id,
            amount=amount,
            date_from=date_from,
            date_to=date_to,
            frequency=frequency,
            repeat_until=repeat_until,
            repeat_anchor_day=anchor_day,
            visibility=visibility,
            account_id=account_id,
        )

    async def _get_owned(
        self, actor: User, planned_income_id: uuid.UUID
    ) -> PlannedIncome:
        planned_income = await self.planned_incomes.get(planned_income_id)
        if planned_income is None or planned_income.user_id != actor.id:
            raise PlannedIncomeNotFoundError
        return planned_income

    async def get_visible(
        self, actor: User, planned_income_id: uuid.UUID
    ) -> PlannedIncome:
        """
        Fetch a planned income ``actor`` is allowed to read.

        :param actor: user requesting the planned income.
        :param planned_income_id: planned income to fetch.
        :raises PlannedIncomeNotFoundError: if it doesn't exist or isn't
            visible to ``actor``.
        :return: the planned income.
        """
        planned_income = await self.planned_incomes.get(planned_income_id)
        if planned_income is None:
            raise PlannedIncomeNotFoundError
        visibility_service = VisibilityService(actor.id, self.session)
        if not await visibility_service.can_view(
            planned_income.user_id, planned_income.visibility
        ):
            raise PlannedIncomeNotFoundError
        return planned_income

    async def update(
        self, actor: User, planned_income_id: uuid.UUID, **fields: object
    ) -> PlannedIncome:
        """
        Update fields on a planned income owned by ``actor``.

        :param actor: user requesting the update.
        :param planned_income_id: planned income to update.
        :param fields: field values to set.
        :raises PlannedIncomeNotFoundError: if it isn't owned by ``actor``.
        :raises InvalidAccountError: if ``account_id`` isn't ``actor``'s.
        :raises InvalidRepeatError: if it would repeat without ``date_from``.
        :return: the updated planned income.
        """
        planned_income = await self._get_owned(actor, planned_income_id)
        if fields.get("account_id") is not None:
            await self._check_account(actor, cast(uuid.UUID, fields["account_id"]))
        if fields.keys() & {"frequency", "date_from"}:
            fields["repeat_anchor_day"] = check_repeat(
                cast(
                    RecurrenceFrequency | None,
                    fields.get("frequency", planned_income.frequency),
                ),
                cast(date | None, fields.get("date_from", planned_income.date_from)),
            )
        return cast(
            PlannedIncome,
            await self.planned_incomes.update(planned_income_id, **fields),
        )

    async def delete(self, actor: User, planned_income_id: uuid.UUID) -> None:
        """
        Delete a planned income owned by ``actor``.

        :param actor: user requesting the deletion.
        :param planned_income_id: planned income to delete.
        :raises PlannedIncomeNotFoundError: if it isn't owned by ``actor``.
        """
        await self._get_owned(actor, planned_income_id)
        await self.planned_incomes.delete(planned_income_id)

    async def list_planned_incomes(
        self, actor: User, *, scope: str = "me"
    ) -> list[PlannedIncome]:
        """
        List planned incomes visible to ``actor``.

        :param actor: user requesting the list.
        :param scope: ``"me"`` or ``"family"``.
        :return: matching planned incomes.
        """
        visibility_service = VisibilityService(actor.id, self.session)
        owner_ids = await visibility_service.visible_owner_ids(scope=scope)
        return await self.planned_incomes.list_visible(actor.id, owner_ids)

    async def list_realise_candidates(
        self, actor: User, planned_income_id: uuid.UUID
    ) -> list[Income]:
        """
        Suggest existing incomes a planned income could be realised against.

        :param actor: user requesting the candidates.
        :param planned_income_id: planned income to suggest candidates for.
        :raises PlannedIncomeNotFoundError: if it isn't owned by ``actor``.
        :return: candidate incomes, most recent first.
        """
        planned_income = await self._get_owned(actor, planned_income_id)
        return await self.income_service.list_realise_candidates(
            actor, planned_income.category_id
        )

    async def realise(
        self,
        actor: User,
        planned_income_id: uuid.UUID,
        *,
        existing_income_id: uuid.UUID | None = None,
        income_overrides: dict[str, Any] | None = None,
    ) -> PlannedIncome:
        """
        Mark a planned income as received, linking it to a real income.

        Two paths: merge into an income that's already recorded, or
        create a brand-new one from the planned income's own fields.

        :param actor: user requesting the realisation.
        :param planned_income_id: planned income being realised.
        :param existing_income_id: an existing income owned by ``actor``
            to link instead of creating a new one -- typically one of
            :meth:`list_realise_candidates`'s results, though any income
            id the caller already knows works too.
        :param income_overrides: for the create-a-new-income path only;
            ``account_id`` falls back to the planned income's own account
            and is **required** if neither is set. ``category_id``/``amount``/
            ``received_at``/``visibility`` fall back to the planned income's own values
            if omitted.
        :raises PlannedIncomeNotFoundError: if it isn't owned by ``actor``.
        :raises InvalidIncomeError: if ``existing_income_id`` isn't owned
            by ``actor``.
        :raises MissingAccountError: if creating a new income without an
            ``account_id`` override and none is planned.
        :return: the realised planned income; a repeating one stays ``PLANNED``
            and moves to its next window, unless ``repeat_until`` is passed.
        """
        planned_income = await self._get_owned(actor, planned_income_id)

        if existing_income_id is not None:
            try:
                income = await self.income_service.update(
                    actor,
                    existing_income_id,
                    planned_income_id=planned_income.id,
                )
            except IncomeNotFoundError as exc:
                raise InvalidIncomeError from exc
        else:
            overrides = dict(income_overrides or {})
            account_id = overrides.get("account_id") or planned_income.account_id
            if account_id is None:
                raise MissingAccountError
            income = await self.income_service.create(
                actor,
                account_id=account_id,
                category_id=overrides.get("category_id", planned_income.category_id),
                amount=overrides.get("amount", planned_income.amount),
                received_at=overrides.get(
                    "received_at", planned_income.date_from or date.today()
                ),
                visibility=overrides.get("visibility", planned_income.visibility),
                planned_income_id=planned_income.id,
            )

        changes: dict[str, Any] = {
            "status": PlanStatus.REALISED,
            "realised_income_id": income.id,
        }
        if (
            planned_income.frequency is not None
            and planned_income.date_from is not None
        ):
            start, end = next_window(
                planned_income.frequency,
                planned_income.repeat_anchor_day,
                planned_income.date_from,
                planned_income.date_to,
            )
            if (
                planned_income.repeat_until is None
                or start <= planned_income.repeat_until
            ):
                changes.update(status=PlanStatus.PLANNED, date_from=start, date_to=end)
        return cast(
            PlannedIncome,
            await self.planned_incomes.update(planned_income.id, **changes),
        )
