from httpx import AsyncClient
from starlette import status


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


async def _salary_category_id(client: AsyncClient) -> int:
    response = await client.get("/api/v1/categories", params={"kind": "income"})
    category_id: int = next(c["id"] for c in response.json() if c["name"] == "Salary")
    return category_id


async def test_create_and_list_income(client: AsyncClient) -> None:
    """A created income shows up in the user's own list."""
    await _register_and_login(client, "inc1@example.com")
    account_id = await _create_account(client)
    category_id = await _salary_category_id(client)

    create_response = await client.post(
        "/api/v1/incomes",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "3400.00",
            "received_at": "2026-09-25",
            "description": "Salary",
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    list_response = await client.get("/api/v1/incomes")
    descriptions = {i["description"] for i in list_response.json()}
    assert "Salary" in descriptions


async def test_create_income_against_foreign_account_rejected(
    client: AsyncClient,
) -> None:
    """An income can't be filed against an account that isn't the user's."""
    await _register_and_login(client, "inc2@example.com")
    category_id = await _salary_category_id(client)

    response = await client.post(
        "/api/v1/incomes",
        json={
            "account_id": "00000000-0000-0000-0000-000000000000",
            "category_id": category_id,
            "amount": "100.00",
            "received_at": "2026-09-25",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_update_and_delete_income(client: AsyncClient) -> None:
    """An owner can update and then delete their own income."""
    await _register_and_login(client, "inc3@example.com")
    account_id = await _create_account(client)
    category_id = await _salary_category_id(client)
    created = await client.post(
        "/api/v1/incomes",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "100.00",
            "received_at": "2026-09-25",
        },
    )
    income_id = created.json()["id"]

    update_response = await client.patch(
        f"/api/v1/incomes/{income_id}", json={"amount": "150.00"}
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["amount"] == "150.00"

    delete_response = await client.delete(f"/api/v1/incomes/{income_id}")
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT


async def test_list_filters_by_date_range(client: AsyncClient) -> None:
    """Listing filters correctly by date_from/date_to."""
    await _register_and_login(client, "inc4@example.com")
    account_id = await _create_account(client)
    category_id = await _salary_category_id(client)
    await client.post(
        "/api/v1/incomes",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "100.00",
            "received_at": "2026-01-01",
        },
    )
    await client.post(
        "/api/v1/incomes",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "200.00",
            "received_at": "2026-09-01",
        },
    )

    response = await client.get(
        "/api/v1/incomes",
        params={"date_from": "2026-08-01", "date_to": "2026-09-30"},
    )

    assert len(response.json()) == 1
    assert response.json()[0]["amount"] == "200.00"
