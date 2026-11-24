import calendar
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.account_query import AccountQuery
from app.dal.category_query import CategoryQuery
from app.dal.recurring_occurrence_query import RecurringOccurrenceQuery
from app.dal.recurring_transaction_query import RecurringTransactionQuery
from app.db.sql.models.enums import (
    CategoryKind,
    PlanStatus,
    RecurrenceFrequency,
    Visibility,
)
from app.db.sql.models.recurring_transaction import (
    RecurringOccurrence,
    RecurringTransaction,
)
from app.db.sql.models.users import User
from app.services.income_service import IncomeNotFoundError, IncomeService
from app.services.spent_service import SpentNotFoundError, SpentService
from app.services.visibility_service import VisibilityService

#: Safety valve for the catch-up loop in ``generate_due_occurrences`` -- a malformed
#: or very-long-neglected rule stops generating occurrences after this
#: many, rather than looping indefinitely.
MAX_CATCH_UP_OCCURRENCES = 366


class RecurringTransactionNotFoundError(Exception):
    """Raised when a recurring rule isn't visible/owned."""


class InvalidAccountError(Exception):
    """Raised when a rule is filed against an account the actor doesn't own."""


class OccurrenceNotFoundError(Exception):
    """Raised when an occurrence doesn't exist or isn't owned by the actor."""


class OccurrenceAlreadyCompletedError(Exception):
    """Raised when confirming an occurrence that is already confirmed."""


class OccurrenceNotCompletedError(Exception):
    """Raised when editing the completion date of an unconfirmed occurrence."""


class InvalidLinkedRecordError(Exception):
    """Raised when the spent/income to link isn't the actor's or wrong kind."""


class CategoryKindMismatchError(Exception):
    """Raised when a rule's kind doesn't match its category's own kind."""


def compute_next_occurrence(
    *,
    frequency: RecurrenceFrequency,
    interval: int,
    day_of_month: int | None,
    weekday: int | None,
    after: date,
) -> date:
    """
    Compute the next occurrence strictly after ``after``.

    Pure function -- no db/session -- so recurrence math (month/weekday
    anchoring, end-of-month clamping) is testable without a database or
    a real cron tick.

    :param frequency: how often the rule repeats.
    :param interval: repeat every N ``frequency`` units.
    :param day_of_month: anchor day for ``MONTHLY``/``YEARLY`` (clamped
        to the target month's last day, e.g. 31 in February -> 28/29).
    :param weekday: anchor weekday (0=Monday) for ``WEEKLY``.
    :param after: the occurrence to step forward from.
    :return: the next occurrence's date.
    """
    if frequency == RecurrenceFrequency.DAILY:
        return date.fromordinal(after.toordinal() + interval)
    if frequency == RecurrenceFrequency.WEEKLY:
        candidate = date.fromordinal(after.toordinal() + interval * 7)
        if weekday is not None:
            candidate = date.fromordinal(
                candidate.toordinal() + (weekday - candidate.weekday()) % 7
            )
        return candidate
    if frequency == RecurrenceFrequency.MONTHLY:
        return _add_months(after, interval, day_of_month)
    return _add_months(after, interval * 12, day_of_month)


def _add_months(base: date, months: int, day_of_month: int | None) -> date:
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = day_of_month if day_of_month is not None else base.day
    day = min(day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class RecurringTransactionService:
    """
    Business logic for repeatable spents/incomes (salary, taxes, ...).

    Builds its own :class:`~app.dal.recurring_transaction_query.
    RecurringTransactionQuery` and :class:`~app.dal.user_query.UserQuery`
    from the db session it's given, and reuses :class:`~app.services.
    spent_service.SpentService`/:class:`~app.services.income_service.
    IncomeService` for creating the spents/incomes a rule realises into
    -- callers never construct a query object themselves, and creation
    logic isn't duplicated.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.recurring = RecurringTransactionQuery(session)
        self.occurrences = RecurringOccurrenceQuery(session)
        self.categories = CategoryQuery(session)
        self.spent_service = SpentService(session)
        self.income_service = IncomeService(session)

    async def _check_category_kind(self, kind: CategoryKind, category_id: int) -> None:
        category = await self.categories.get(category_id)
        if category is None or category.kind != kind:
            raise CategoryKindMismatchError

    async def create(
        self,
        actor: User,
        *,
        account_id: uuid.UUID,
        kind: CategoryKind,
        category_id: int,
        amount: Decimal,
        frequency: RecurrenceFrequency,
        start_date: date,
        interval: int = 1,
        day_of_month: int | None = None,
        weekday: int | None = None,
        end_date: date | None = None,
        description: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
    ) -> RecurringTransaction:
        """
        Create a recurring rule owned by ``actor``.

        :param actor: the rule's owner.
        :param account_id: account each occurrence posts to -- must
            belong to ``actor``.
        :param kind: expense or income.
        :param category_id: category to file each occurrence under.
        :param amount: amount per occurrence.
        :param frequency: how often the rule repeats.
        :param start_date: date of the rule's first occurrence.
        :param interval: repeat every N ``frequency`` units.
        :param day_of_month: anchor day for ``MONTHLY``/``YEARLY``.
        :param weekday: anchor weekday (0=Monday) for ``WEEKLY``.
        :param end_date: last date the rule may occur on, if any.
        :param description: free-text note.
        :param visibility: who besides ``actor`` may see each occurrence.
        :raises InvalidAccountError: if ``account_id`` isn't ``actor``'s.
        :raises CategoryKindMismatchError: if ``category_id`` isn't a
            category of ``kind``.
        :return: the created rule.
        """
        await self._check_account(actor, account_id)
        await self._check_category_kind(kind, category_id)
        return await self.recurring.create(
            user_id=actor.id,
            account_id=account_id,
            kind=kind,
            category_id=category_id,
            amount=amount,
            description=description,
            visibility=visibility,
            frequency=frequency,
            interval=interval,
            day_of_month=day_of_month,
            weekday=weekday,
            start_date=start_date,
            end_date=end_date,
            # The first occurrence *is* start_date -- see the note in
            # the build plan on why this isn't run through
            # compute_next_occurrence.
            next_run_at=start_date,
            is_active=True,
        )

    async def _check_account(self, actor: User, account_id: uuid.UUID) -> None:
        account = await AccountQuery(self.session).get(account_id)
        if account is None or account.user_id != actor.id:
            raise InvalidAccountError

    async def _get_owned(
        self, actor: User, recurring_transaction_id: uuid.UUID
    ) -> RecurringTransaction:
        rule = await self.recurring.get(recurring_transaction_id)
        if rule is None or rule.user_id != actor.id:
            raise RecurringTransactionNotFoundError
        return rule

    async def update(
        self, actor: User, recurring_transaction_id: uuid.UUID, **fields: object
    ) -> RecurringTransaction:
        """
        Update fields on a recurring rule owned by ``actor``.

        :param actor: user requesting the update.
        :param recurring_transaction_id: rule to update.
        :param fields: field values to set.
        :raises RecurringTransactionNotFoundError: if it isn't owned by
            ``actor``.
        :raises InvalidAccountError: if ``account_id`` is being changed
            to one that isn't ``actor``'s.
        :raises CategoryKindMismatchError: if the resulting ``kind``/
            ``category_id`` pair wouldn't match.
        :return: the updated rule.
        """
        rule = await self._get_owned(actor, recurring_transaction_id)
        if "account_id" in fields:
            await self._check_account(actor, cast(uuid.UUID, fields["account_id"]))
        if "kind" in fields or "category_id" in fields:
            effective_kind = cast(CategoryKind, fields.get("kind", rule.kind))
            effective_category_id = cast(
                int, fields.get("category_id", rule.category_id)
            )
            await self._check_category_kind(effective_kind, effective_category_id)
        return cast(
            RecurringTransaction,
            await self.recurring.update(recurring_transaction_id, **fields),
        )

    async def pause(
        self, actor: User, recurring_transaction_id: uuid.UUID
    ) -> RecurringTransaction:
        """
        Pause a recurring rule without deleting it.

        :param actor: user requesting the pause.
        :param recurring_transaction_id: rule to pause.
        :raises RecurringTransactionNotFoundError: if it isn't owned by
            ``actor``.
        :return: the paused rule.
        """
        return await self.update(actor, recurring_transaction_id, is_active=False)

    async def resume(
        self, actor: User, recurring_transaction_id: uuid.UUID
    ) -> RecurringTransaction:
        """
        Resume a paused recurring rule.

        :param actor: user requesting the resume.
        :param recurring_transaction_id: rule to resume.
        :raises RecurringTransactionNotFoundError: if it isn't owned by
            ``actor``.
        :return: the resumed rule.
        """
        return await self.update(actor, recurring_transaction_id, is_active=True)

    async def delete(self, actor: User, recurring_transaction_id: uuid.UUID) -> None:
        """
        Delete a recurring rule owned by ``actor``.

        Its occurrences go with it; spents/incomes they were confirmed into
        keep existing, just losing their ``recurring_occurrence_id`` tag.

        :param actor: user requesting the deletion.
        :param recurring_transaction_id: rule to delete.
        :raises RecurringTransactionNotFoundError: if it isn't owned by
            ``actor``.
        """
        await self._get_owned(actor, recurring_transaction_id)
        await self.recurring.delete(recurring_transaction_id)

    async def list_recurring(
        self, actor: User, *, scope: str = "me"
    ) -> list[RecurringTransaction]:
        """
        List recurring rules visible to ``actor``.

        :param actor: user requesting the list.
        :param scope: ``"me"`` or ``"family"``.
        :return: matching rules.
        """
        visibility_service = VisibilityService(actor.id, self.session)
        owner_ids = await visibility_service.visible_owner_ids(scope=scope)
        return await self.recurring.list_visible(actor.id, owner_ids)

    async def generate_due_occurrences(
        self, as_of: date | None = None
    ) -> list[uuid.UUID]:
        """
        Generate a pending occurrence for every due date of every active rule.

        Not actor-scoped -- called only from the Taskiq task. Catches up
        rather than skipping: a rule whose ``next_run_at`` is several
        occurrences in the past gets one ``PLANNED`` occurrence per missed
        date, so a missed paycheck surfaces for confirmation instead of
        vanishing. Nothing is posted to the ledger here.

        :param as_of: the date to sweep as of; defaults to today.
        :return: ids of every occurrence created.
        """
        as_of = as_of or date.today()
        created_ids: list[uuid.UUID] = []

        for rule in await self.recurring.due(as_of):
            occurrence_date = rule.next_run_at
            last_generated_at = rule.last_generated_at
            is_active = True

            for _ in range(MAX_CATCH_UP_OCCURRENCES):
                if occurrence_date > as_of:
                    break

                occurrence = await self.occurrences.create(
                    recurring_transaction_id=rule.id,
                    due_date=occurrence_date,
                    status=PlanStatus.PLANNED,
                )
                created_ids.append(occurrence.id)
                last_generated_at = occurrence_date

                occurrence_date = compute_next_occurrence(
                    frequency=rule.frequency,
                    interval=rule.interval,
                    day_of_month=rule.day_of_month,
                    weekday=rule.weekday,
                    after=occurrence_date,
                )
                if rule.end_date is not None and occurrence_date > rule.end_date:
                    is_active = False
                    break

            await self.recurring.update(
                rule.id,
                next_run_at=occurrence_date,
                last_generated_at=last_generated_at,
                is_active=is_active,
            )

        return created_ids

    async def list_occurrences(
        self,
        actor: User,
        *,
        scope: str = "me",
        status: PlanStatus | None = None,
    ) -> list[RecurringOccurrence]:
        """
        List occurrences visible to ``actor``.

        :param actor: user requesting the list.
        :param scope: ``"me"`` or ``"family"``.
        :param status: ``PLANNED`` for the confirmation queue, ``REALISED``
            for history, ``None`` for both.
        :return: matching occurrences, earliest due date first.
        """
        visibility_service = VisibilityService(actor.id, self.session)
        owner_ids = await visibility_service.visible_owner_ids(scope=scope)
        return await self.occurrences.list_visible(actor.id, owner_ids, status=status)

    async def _get_owned_occurrence(
        self, actor: User, occurrence_id: uuid.UUID
    ) -> tuple[RecurringOccurrence, RecurringTransaction]:
        occurrence = await self.occurrences.get(occurrence_id)
        if occurrence is None:
            raise OccurrenceNotFoundError
        rule = await self.recurring.get(occurrence.recurring_transaction_id)
        if rule is None or rule.user_id != actor.id:
            raise OccurrenceNotFoundError
        return occurrence, rule

    async def complete_occurrence(
        self,
        actor: User,
        occurrence_id: uuid.UUID,
        *,
        completed_at: date | None = None,
        existing_spent_id: uuid.UUID | None = None,
        existing_income_id: uuid.UUID | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> RecurringOccurrence:
        """
        Confirm that an occurrence actually happened.

        Two paths: link an already-recorded spent/income, or post a new
        one from the rule's own fields (``overrides`` may adjust
        ``amount``/``account_id``/``category_id`` for this occurrence).
        The posted record is dated ``completed_at``, not ``due_date``.

        :param actor: user confirming -- must own the rule.
        :param occurrence_id: occurrence being confirmed.
        :param completed_at: the date it happened; defaults to today.
        :param existing_spent_id: existing spent to link (expense rules).
        :param existing_income_id: existing income to link (income rules).
        :param overrides: per-occurrence field overrides for the new record.
        :raises OccurrenceNotFoundError: if it isn't the actor's.
        :raises OccurrenceAlreadyCompletedError: if already confirmed.
        :raises InvalidLinkedRecordError: if the existing record isn't the
            actor's, or its kind doesn't match the rule's.
        :return: the confirmed occurrence.
        """
        occurrence, rule = await self._get_owned_occurrence(actor, occurrence_id)
        if occurrence.status == PlanStatus.REALISED:
            raise OccurrenceAlreadyCompletedError
        completed_at = completed_at or date.today()
        fields = dict(overrides or {})
        spent_id: uuid.UUID | None = None
        income_id: uuid.UUID | None = None

        if rule.kind == CategoryKind.EXPENSE:
            if existing_income_id is not None:
                raise InvalidLinkedRecordError
            if existing_spent_id is not None:
                try:
                    spent = await self.spent_service.update(
                        actor,
                        existing_spent_id,
                        recurring_occurrence_id=occurrence.id,
                    )
                except SpentNotFoundError as exc:
                    raise InvalidLinkedRecordError from exc
            else:
                spent = await self.spent_service.create(
                    actor,
                    account_id=fields.get("account_id", rule.account_id),
                    category_id=fields.get("category_id", rule.category_id),
                    amount=fields.get("amount", rule.amount),
                    spent_at=completed_at,
                    description=rule.description,
                    visibility=rule.visibility,
                    recurring_occurrence_id=occurrence.id,
                )
            spent_id = spent.id
        else:
            if existing_spent_id is not None:
                raise InvalidLinkedRecordError
            if existing_income_id is not None:
                try:
                    income = await self.income_service.update(
                        actor,
                        existing_income_id,
                        recurring_occurrence_id=occurrence.id,
                    )
                except IncomeNotFoundError as exc:
                    raise InvalidLinkedRecordError from exc
            else:
                income = await self.income_service.create(
                    actor,
                    account_id=fields.get("account_id", rule.account_id),
                    category_id=fields.get("category_id", rule.category_id),
                    amount=fields.get("amount", rule.amount),
                    received_at=completed_at,
                    description=rule.description,
                    visibility=rule.visibility,
                    recurring_occurrence_id=occurrence.id,
                )
            income_id = income.id

        return cast(
            RecurringOccurrence,
            await self.occurrences.update(
                occurrence.id,
                status=PlanStatus.REALISED,
                completed_at=completed_at,
                spent_id=spent_id,
                income_id=income_id,
            ),
        )

    async def update_completed_at(
        self, actor: User, occurrence_id: uuid.UUID, new_date: date
    ) -> RecurringOccurrence:
        """
        Edit the completion date of an already-confirmed occurrence.

        The linked spent/income is re-dated too, so the two never drift.

        :param actor: user editing -- must own the rule.
        :param occurrence_id: occurrence to edit.
        :param new_date: the corrected completion date.
        :raises OccurrenceNotFoundError: if it isn't the actor's.
        :raises OccurrenceNotCompletedError: if it hasn't been confirmed yet.
        :return: the updated occurrence.
        """
        occurrence, _ = await self._get_owned_occurrence(actor, occurrence_id)
        if occurrence.status != PlanStatus.REALISED:
            raise OccurrenceNotCompletedError
        if occurrence.spent_id is not None:
            await self.spent_service.update(
                actor, occurrence.spent_id, spent_at=new_date
            )
        if occurrence.income_id is not None:
            await self.income_service.update(
                actor, occurrence.income_id, received_at=new_date
            )
        return cast(
            RecurringOccurrence,
            await self.occurrences.update(occurrence.id, completed_at=new_date),
        )
