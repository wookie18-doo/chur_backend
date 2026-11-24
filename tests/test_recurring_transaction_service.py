from datetime import date

from app.db.sql.models.enums import RecurrenceFrequency
from app.services.recurring_transaction_service import compute_next_occurrence


def test_daily_steps_by_interval() -> None:
    """A daily rule advances by exactly `interval` days."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.DAILY,
        interval=3,
        day_of_month=None,
        weekday=None,
        after=date(2026, 9, 26),
    )

    assert result == date(2026, 9, 29)


def test_weekly_anchors_to_weekday() -> None:
    """A weekly rule lands back on its anchor weekday."""
    # 2026-09-26 is a Saturday (weekday=5).
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.WEEKLY,
        interval=1,
        day_of_month=None,
        weekday=0,  # Monday
        after=date(2026, 9, 26),
    )

    assert result.weekday() == 0
    assert result == date(2026, 10, 5)


def test_weekly_without_anchor_just_adds_weeks() -> None:
    """A weekly rule with no weekday anchor steps by whole weeks."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.WEEKLY,
        interval=2,
        day_of_month=None,
        weekday=None,
        after=date(2026, 9, 26),
    )

    assert result == date(2026, 10, 10)


def test_monthly_anchors_to_day_of_month() -> None:
    """A monthly rule lands on the anchor day of the next month."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        interval=1,
        day_of_month=25,
        weekday=None,
        after=date(2026, 9, 25),
    )

    assert result == date(2026, 10, 25)


def test_monthly_clamps_to_end_of_shorter_month() -> None:
    """day_of_month=31 in a 30-day (or shorter) month clamps to its last day."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        interval=1,
        day_of_month=31,
        weekday=None,
        after=date(2026, 1, 31),
    )

    assert result == date(2026, 2, 28)


def test_monthly_clamps_to_feb_29_on_leap_year() -> None:
    """The clamp respects leap years."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        interval=1,
        day_of_month=31,
        weekday=None,
        after=date(2028, 1, 31),
    )

    assert result == date(2028, 2, 29)


def test_monthly_interval_greater_than_one() -> None:
    """A quarterly rule (interval=3) skips two months forward."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        interval=3,
        day_of_month=15,
        weekday=None,
        after=date(2026, 1, 15),
    )

    assert result == date(2026, 4, 15)


def test_monthly_rolls_over_year_boundary() -> None:
    """Stepping past December correctly rolls into the next year."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        interval=1,
        day_of_month=25,
        weekday=None,
        after=date(2026, 12, 25),
    )

    assert result == date(2027, 1, 25)


def test_yearly_anchors_to_day_of_month() -> None:
    """A yearly rule lands on the same day/month one year later."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.YEARLY,
        interval=1,
        day_of_month=1,
        weekday=None,
        after=date(2026, 4, 1),
    )

    assert result == date(2027, 4, 1)


def test_yearly_interval_greater_than_one() -> None:
    """A biennial rule (interval=2) steps two years forward."""
    result = compute_next_occurrence(
        frequency=RecurrenceFrequency.YEARLY,
        interval=2,
        day_of_month=1,
        weekday=None,
        after=date(2026, 4, 1),
    )

    assert result == date(2028, 4, 1)
