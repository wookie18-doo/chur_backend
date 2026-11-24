from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _second_client(fastapi_app: FastAPI) -> AsyncClient:
    """Build another client against the same app, with its own cookie jar."""
    return AsyncClient(
        transport=ASGITransport(fastapi_app), base_url="http://test", timeout=2.0
    )


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


async def test_summary_totals_and_diff(client: AsyncClient) -> None:
    """total_income, total_spent, and diff reflect the period's entries."""
    await _register_and_login(client, "rep1@example.com")
    account_id = await _create_account(client)
    expense_category = await _category_id(client, "expense", "Groceries")
    income_category = await _category_id(client, "income", "Salary")

    await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": expense_category,
            "amount": "100.00",
            "spent_at": "2026-09-10",
        },
    )
    await client.post(
        "/api/v1/incomes",
        json={
            "account_id": account_id,
            "category_id": income_category,
            "amount": "400.00",
            "received_at": "2026-09-05",
        },
    )

    response = await client.get(
        "/api/v1/reports/summary",
        params={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    )

    body = response.json()
    assert body["total_income"] == "400.00"
    assert body["total_spent"] == "100.00"
    assert body["diff"] == "300.00"


async def test_summary_empty_range_returns_zeros(client: AsyncClient) -> None:
    """A date range with no entries returns zeroed totals, not an error."""
    await _register_and_login(client, "rep2@example.com")

    response = await client.get(
        "/api/v1/reports/summary",
        params={"date_from": "2020-01-01", "date_to": "2020-01-31"},
    )

    body = response.json()
    assert body["total_income"] == "0"
    assert body["total_spent"] == "0"
    assert body["diff"] == "0"


async def test_me_scope_excludes_family_members_totals(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """Scope "me" only counts the requester's own entries."""
    await _register_and_login(client, "rep3owner@example.com")
    account_id = await _create_account(client)
    category_id = await _category_id(client, "expense", "Groceries")
    await client.post("/api/v1/families", json={"name": "The Smiths"})
    await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "100.00",
            "spent_at": "2026-09-10",
            "visibility": "family",
        },
    )

    async with _second_client(fastapi_app) as member:
        await _register_and_login(member, "rep3member@example.com")
        member_user_id = (await member.get("/api/v1/users/me")).json()["id"]
        await client.post("/api/v1/families/members", json={"user_id": member_user_id})
        member_account_id = await _create_account(member, "Cash")
        await member.post(
            "/api/v1/spents",
            json={
                "account_id": member_account_id,
                "category_id": category_id,
                "amount": "40.00",
                "spent_at": "2026-09-11",
                "visibility": "family",
            },
        )

        me_scope = await member.get(
            "/api/v1/reports/summary",
            params={
                "date_from": "2026-09-01",
                "date_to": "2026-09-30",
                "scope": "me",
            },
        )
        family_scope = await member.get(
            "/api/v1/reports/summary",
            params={
                "date_from": "2026-09-01",
                "date_to": "2026-09-30",
                "scope": "family",
            },
        )

    assert me_scope.json()["total_spent"] == "40.00"
    assert family_scope.json()["total_spent"] == "140.00"


async def test_group_by_category_and_account(client: AsyncClient) -> None:
    """by_category and by_account sums match the underlying entries."""
    await _register_and_login(client, "rep4@example.com")
    account_a = await _create_account(client, "Wise EUR")
    account_b = await _create_account(client, "Cash")
    groceries = await _category_id(client, "expense", "Groceries")
    transport = await _category_id(client, "expense", "Transport")

    await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_a,
            "category_id": groceries,
            "amount": "30.00",
            "spent_at": "2026-09-10",
        },
    )
    await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_b,
            "category_id": transport,
            "amount": "15.00",
            "spent_at": "2026-09-11",
        },
    )

    response = await client.get(
        "/api/v1/reports/summary",
        params={
            "date_from": "2026-09-01",
            "date_to": "2026-09-30",
            "group_by_category": "true",
            "group_by_account": "true",
        },
    )

    body = response.json()
    assert body["by_category"][str(groceries)] == "30.00"
    assert body["by_category"][str(transport)] == "15.00"
    assert body["by_account"][account_a]["spent"] == "30.00"
    assert body["by_account"][account_b]["spent"] == "15.00"
