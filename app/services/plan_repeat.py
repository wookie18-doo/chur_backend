from datetime import date
from typing import Any

from app.db.sql.models.enums import RecurrenceFrequency
from app.services.recurring_transaction_service import compute_next_occurrence


class InvalidRepeatError(Exception):
    """Raised when a repeat is daily or has no date to repeat from."""


def next_window(
    frequency: RecurrenceFrequency,
    anchor_day: int | None,
    start: date,
    end: date | None,
) -> tuple[date, date | None]:
    """
    Shift a planned date window forward by one period.

    The window keeps its length in days, so a due-date range stays the
    same size. Stepping from the planned ``start`` (never the date it was
    actually realised on) keeps the schedule fixed.

    :param frequency: repeat period.
    :param anchor_day: day of month to return to after end-of-month clamping.
    :param start: current window start.
    :param end: current window end, if any.
    :return: the next window's start and end.
    """
    next_start = compute_next_occurrence(
        frequency=frequency,
        interval=1,
        day_of_month=anchor_day,
        weekday=None,
        after=start,
    )
    next_end = None if end is None else next_start + (end - start)
    return next_start, next_end


def check_repeat(
    repeat: RecurrenceFrequency | None, base_date: date | None
) -> int | None:
    """
    Validate a repeat setting and derive its month-end anchor day.

    :param repeat: the repeat period, if any.
    :param base_date: the date the schedule steps from.
    :raises InvalidRepeatError: if ``repeat`` is daily or lacks ``base_date``.
    :return: the anchor day, or ``None`` when there is no repeat.
    """
    if repeat is None:
        return None
    if repeat == RecurrenceFrequency.DAILY or base_date is None:
        raise InvalidRepeatError
    return base_date.day


def repeat_fields(data: dict[str, Any]) -> dict[str, Any]:
    """
    Turn an API body's ``repeat`` flag into service-level ``frequency``.

    :param data: dumped request body (with ``exclude_unset`` for updates).
    :return: the same fields with ``repeat`` removed; ``repeat=False``
        clears ``frequency``.
    """
    fields = dict(data)
    if "repeat" in fields and not fields.pop("repeat"):
        fields["frequency"] = None
    return fields
