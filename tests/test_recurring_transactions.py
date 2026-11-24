import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette import status

from app.dal.account_query import AccountQuery
from app.dal.category_query import CategoryQuery
from app.dal.user_query import UserQuery
from app.db.sql.models.enums import (
    AccountKind,
    CategoryKind,
    PlanStatus,
    RecurrenceFrequency,
)
from app.services.recurring_transaction_service import RecurringTransactionService


async def _register_and_login(client: AsyncClient, email: str) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )


async def _create_account(client: AsyncClient, name: str = "Wise EUR") -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": name, "kind": "bank", "currency": "EUR"},
    )
    account_id: str = response.json()["id"]
    return account_id


async def _category_id(client: AsyncClient, kind: str, name: str) -> int:
    response = await client.get("/api/v1/categories", params={"kind": kind})
    category_id: int = next(c["id"] for c in response.json() if c["name"] == name)
    return category_id


async def test_create_pause_resume_delete(client: AsyncClient) -> None:
    """The full lifecycle of a recurring rule via the API."""
    await _register_and_login(client, "rt1@example.com")
    account_id = await _create_account(client)
    category_id = await _category_id(client, "income", "Salary")

    created = await client.post(
        "/api/v1/recurring",
        json={
            "account_id": account_id,
            "kind": "income",
            "category_id": category_id,
            "amount": "3400.00",
            "frequency": "monthly",
            "day_of_month": 25,
            "start_date": "2026-09-25",
        },
    )
    assert created.status_code == status.HTTP_201_CREATED
    rule_id = created.json()["id"]
    assert created.json()["next_run_at"] == "2026-09-25"
    assert created.json()["is_active"] is True

    pause_response = await client.post(f"/api/v1/recurring/{rule_id}/pause")
    assert pause_response.json()["is_active"] is False

    resume_response = await client.post(f"/api/v1/recurring/{rule_id}/resume")
    assert resume_response.json()["is_active"] is True

    delete_response = await client.delete(f"/api/v1/recurring/{rule_id}")
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT


async def test_create_rejects_kind_category_mismatch(client: AsyncClient) -> None:
    """An income category can't back an expense rule, and vice versa."""
    await _register_and_login(client, "rt2@example.com")
    account_id = await _create_account(client)
    income_category = await _category_id(client, "income", "Salary")

    response = await client.post(
        "/api/v1/recurring",
        json={
            "account_id": account_id,
            "kind": "expense",
            "category_id": income_category,
            "amount": "10.00",
            "frequency": "monthly",
            "start_date": "2026-09-25",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_create_rejects_foreign_account(client: AsyncClient) -> None:
    """A rule can't post to an account the user doesn't own."""
    await _register_and_login(client, "rt3@example.com")
    category_id = await _category_id(client, "expense", "Housing")

    response = await client.post(
        "/api/v1/recurring",
        json={
            "account_id": str(uuid.uuid4()),
            "kind": "expense",
            "category_id": category_id,
            "amount": "10.00",
            "frequency": "monthly",
            "start_date": "2026-09-25",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_generate_due_catches_up_missed_occurrences(
    dbsession: AsyncSession,
) -> None:
    """A daily rule overdue since 3 days ago gets an occurrence per missed day.

    next_run_at = today-3, swept as_of today: today-3, today-2, today-1,
    and today itself are all <= as_of, so all four are due -- not three.
    """
    user = await UserQuery(dbsession).create(
        id=uuid.uuid4(),
        email="rt4@example.com",
        hashed_password="not-a-real-hash",  # noqa: S106
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    account = await AccountQuery(dbsession).create(
        user_id=user.id, name="Cash", kind=AccountKind.CASH, currency="EUR"
    )
    category = await CategoryQuery(dbsession).create(
        name="Groceries", kind=CategoryKind.EXPENSE, owner_id=None
    )

    service = RecurringTransactionService(dbsession)
    today = date.today()
    rule = await service.create(
        user,
        account_id=account.id,
        kind=CategoryKind.EXPENSE,
        category_id=cast(int, category.id),
        amount=Decimal("5"),
        frequency=RecurrenceFrequency.DAILY,
        start_date=today - timedelta(days=3),
    )

    created_ids = await service.generate_due_occurrences(as_of=today)

    assert len(created_ids) == 4
    for occurrence_id in created_ids:
        occurrence = await service.occurrences.get(occurrence_id)
        assert occurrence is not None
        assert occurrence.recurring_transaction_id == rule.id
        assert occurrence.status == PlanStatus.PLANNED
        assert occurrence.spent_id is None

    updated_rule = await service.recurring.get(rule.id)
    assert updated_rule is not None
    assert updated_rule.next_run_at == today + timedelta(days=1)
    assert updated_rule.last_generated_at == today


async def test_generate_due_skips_paused_rule(dbsession: AsyncSession) -> None:
    """A paused rule produces nothing, even if overdue."""
    user = await UserQuery(dbsession).create(
        id=uuid.uuid4(),
        email="rt5@example.com",
        hashed_password="not-a-real-hash",  # noqa: S106
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    account = await AccountQuery(dbsession).create(
        user_id=user.id, name="Cash", kind=AccountKind.CASH, currency="EUR"
    )
    category = await CategoryQuery(dbsession).create(
        name="Groceries", kind=CategoryKind.EXPENSE, owner_id=None
    )
    service = RecurringTransactionService(dbsession)
    today = date.today()
    rule = await service.create(
        user,
        account_id=account.id,
        kind=CategoryKind.EXPENSE,
        category_id=cast(int, category.id),
        amount=Decimal("5"),
        frequency=RecurrenceFrequency.DAILY,
        start_date=today - timedelta(days=3),
    )
    await service.pause(user, rule.id)

    created_ids = await service.generate_due_occurrences(as_of=today)

    assert created_ids == []


async def test_generate_due_deactivates_past_end_date(dbsession: AsyncSession) -> None:
    """A rule stops (is_active=False) once its next occurrence exceeds end_date."""
    user = await UserQuery(dbsession).create(
        id=uuid.uuid4(),
        email="rt6@example.com",
        hashed_password="not-a-real-hash",  # noqa: S106
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    account = await AccountQuery(dbsession).create(
        user_id=user.id, name="Cash", kind=AccountKind.CASH, currency="EUR"
    )
    category = await CategoryQuery(dbsession).create(
        name="Groceries", kind=CategoryKind.EXPENSE, owner_id=None
    )
    service = RecurringTransactionService(dbsession)
    today = date.today()
    rule = await service.create(
        user,
        account_id=account.id,
        kind=CategoryKind.EXPENSE,
        category_id=cast(int, category.id),
        amount=Decimal("5"),
        frequency=RecurrenceFrequency.DAILY,
        start_date=today,
        end_date=today,
    )

    created_ids = await service.generate_due_occurrences(as_of=today)

    assert len(created_ids) == 1
    updated_rule = await service.recurring.get(rule.id)
    assert updated_rule is not None
    assert updated_rule.is_active is False


async def _income_rule(client: AsyncClient, email: str) -> tuple[str, str, int]:
    await _register_and_login(client, email)
    account_id = await _create_account(client)
    category_id = await _category_id(client, "income", "Salary")
    created = await client.post(
        "/api/v1/recurring",
        json={
            "account_id": account_id,
            "kind": "income",
            "category_id": category_id,
            "amount": "100.00",
            "frequency": "monthly",
            "day_of_month": 5,
            "start_date": "2026-09-05",
        },
    )
    return created.json()["id"], account_id, category_id


async def test_occurrence_complete_posts_income_on_completed_date(
    client: AsyncClient, dbsession: AsyncSession
) -> None:
    """Confirming posts the income on completed_at, not the due date."""
    rule_id, account_id, _ = await _income_rule(client, "rt7@example.com")
    service = RecurringTransactionService(dbsession)
    ids = await service.generate_due_occurrences(as_of=date(2026, 9, 5))
    assert len(ids) == 1

    queue = await client.get(
        "/api/v1/recurring/occurrences", params={"status": "planned"}
    )
    assert [o["id"] for o in queue.json()] == [str(ids[0])]
    assert queue.json()[0]["recurring_transaction_id"] == rule_id

    done = await client.post(
        f"/api/v1/recurring/occurrences/{ids[0]}/complete",
        json={"completed_at": "2026-09-10", "amount": "120.00"},
    )

    assert done.status_code == status.HTTP_200_OK
    body = done.json()
    assert body["status"] == "realised"
    assert body["due_date"] == "2026-09-05"
    assert body["completed_at"] == "2026-09-10"
    incomes = await client.get("/api/v1/incomes")
    assert [
        (i["received_at"], i["amount"], i["account_id"]) for i in incomes.json()
    ] == [("2026-09-10", "120.00", account_id)]
    assert incomes.json()[0]["recurring_occurrence_id"] == str(ids[0])

    again = await client.post(
        f"/api/v1/recurring/occurrences/{ids[0]}/complete", json={}
    )
    assert again.status_code == status.HTTP_409_CONFLICT


async def test_occurrence_edit_completed_at_redates_income(
    client: AsyncClient, dbsession: AsyncSession
) -> None:
    """Editing a confirmed occurrence's date moves its income too."""
    await _income_rule(client, "rt8@example.com")
    service = RecurringTransactionService(dbsession)
    [occurrence_id] = await service.generate_due_occurrences(as_of=date(2026, 9, 5))

    early = await client.patch(
        f"/api/v1/recurring/occurrences/{occurrence_id}",
        json={"completed_at": "2026-09-12"},
    )
    assert early.status_code == status.HTTP_409_CONFLICT

    await client.post(
        f"/api/v1/recurring/occurrences/{occurrence_id}/complete",
        json={"completed_at": "2026-09-10"},
    )
    edited = await client.patch(
        f"/api/v1/recurring/occurrences/{occurrence_id}",
        json={"completed_at": "2026-09-12"},
    )

    assert edited.status_code == status.HTTP_200_OK
    assert edited.json()["completed_at"] == "2026-09-12"
    incomes = await client.get("/api/v1/incomes")
    assert incomes.json()[0]["received_at"] == "2026-09-12"


async def test_occurrence_links_existing_income_without_duplicating(
    client: AsyncClient, dbsession: AsyncSession
) -> None:
    """Completing against an existing income links it instead of posting."""
    _, account_id, category_id = await _income_rule(client, "rt9@example.com")
    existing = await client.post(
        "/api/v1/incomes",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "100.00",
            "received_at": "2026-09-06",
        },
    )
    [occurrence_id] = await RecurringTransactionService(
        dbsession
    ).generate_due_occurrences(as_of=date(2026, 9, 5))

    done = await client.post(
        f"/api/v1/recurring/occurrences/{occurrence_id}/complete",
        json={"existing_income_id": existing.json()["id"]},
    )

    assert done.json()["income_id"] == existing.json()["id"]
    assert len((await client.get("/api/v1/incomes")).json()) == 1


async def test_occurrences_are_owner_only(
    client: AsyncClient, fastapi_app: FastAPI, dbsession: AsyncSession
) -> None:
    """Another user can neither see nor complete someone else's occurrence."""
    await _income_rule(client, "rt10@example.com")
    [occurrence_id] = await RecurringTransactionService(
        dbsession
    ).generate_due_occurrences(as_of=date(2026, 9, 5))

    async with AsyncClient(
        transport=ASGITransport(fastapi_app), base_url="http://test", timeout=2.0
    ) as other:
        await _register_and_login(other, "rt11@example.com")
        assert (await other.get("/api/v1/recurring/occurrences")).json() == []
        response = await other.post(
            f"/api/v1/recurring/occurrences/{occurrence_id}/complete", json={}
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
