from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette import status


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


async def _groceries_category_id(client: AsyncClient) -> int:
    response = await client.get("/api/v1/categories", params={"kind": "expense"})
    category_id: int = next(
        c["id"] for c in response.json() if c["name"] == "Groceries"
    )
    return category_id


async def test_create_and_list_spent(client: AsyncClient) -> None:
    """A created spent shows up in the user's own list with item_count 0."""
    await _register_and_login(client, "sp1@example.com")
    account_id = await _create_account(client)
    category_id = await _groceries_category_id(client)

    create_response = await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "49.80",
            "spent_at": "2026-09-26",
            "description": "Lidl weekly shop",
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    assert create_response.json()["item_count"] == 0

    list_response = await client.get("/api/v1/spents")
    assert list_response.status_code == status.HTTP_200_OK
    amounts = {s["description"] for s in list_response.json()}
    assert "Lidl weekly shop" in amounts


async def test_create_spent_against_foreign_account_rejected(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """A spent can't be filed against another user's account."""
    async with _second_client(fastapi_app) as owner:
        await _register_and_login(owner, "sp2owner@example.com")
        account_id = await _create_account(owner)

    await _register_and_login(client, "sp2stranger@example.com")
    category_id = await _groceries_category_id(client)

    response = await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "10.00",
            "spent_at": "2026-09-26",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_family_member_can_read_but_not_edit_shared_spent(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """A FAMILY-visibility spent is readable, never writable, by a member."""
    await _register_and_login(client, "sp3owner@example.com")
    account_id = await _create_account(client)
    category_id = await _groceries_category_id(client)
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as member:
        await _register_and_login(member, "sp3member@example.com")
        member_user_id = (await member.get("/api/v1/users/me")).json()["id"]

        add_response = await client.post(
            "/api/v1/families/members", json={"user_id": member_user_id}
        )
        assert add_response.status_code == status.HTTP_201_CREATED

        created = await client.post(
            "/api/v1/spents",
            json={
                "account_id": account_id,
                "category_id": category_id,
                "amount": "20.00",
                "spent_at": "2026-09-26",
                "visibility": "family",
            },
        )
        spent_id = created.json()["id"]

        read_response = await member.get(f"/api/v1/spents/{spent_id}")
        assert read_response.status_code == status.HTTP_200_OK

        write_response = await member.patch(
            f"/api/v1/spents/{spent_id}", json={"amount": "1.00"}
        )
        assert write_response.status_code == status.HTTP_404_NOT_FOUND


async def test_list_filters_by_account_and_category(client: AsyncClient) -> None:
    """Listing filters correctly by account_id and category_id."""
    await _register_and_login(client, "sp4@example.com")
    account_a = await _create_account(client, "Wise EUR")
    account_b = await _create_account(client, "Cash")
    category_id = await _groceries_category_id(client)

    await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_a,
            "category_id": category_id,
            "amount": "10.00",
            "spent_at": "2026-09-01",
        },
    )
    await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_b,
            "category_id": category_id,
            "amount": "5.00",
            "spent_at": "2026-09-02",
        },
    )

    response = await client.get("/api/v1/spents", params={"account_id": account_a})

    assert len(response.json()) == 1
    assert response.json()[0]["account_id"] == account_a


async def test_add_item_shows_in_detail_but_not_list(client: AsyncClient) -> None:
    """Line items appear in the detail view only, list keeps item_count."""
    await _register_and_login(client, "sp5@example.com")
    account_id = await _create_account(client)
    category_id = await _groceries_category_id(client)
    created = await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "49.80",
            "spent_at": "2026-09-26",
        },
    )
    spent_id = created.json()["id"]

    await client.post(
        f"/api/v1/spents/{spent_id}/items",
        json={"name": "Milk", "amount": "2.38", "quantity": "x2"},
    )
    await client.post(
        f"/api/v1/spents/{spent_id}/items",
        json={"name": "Dark chocolate", "amount": "1.49"},
    )

    list_response = await client.get("/api/v1/spents")
    row = next(s for s in list_response.json() if s["id"] == spent_id)
    assert row["item_count"] == 2
    assert "items" not in row

    detail_response = await client.get(f"/api/v1/spents/{spent_id}")
    detail = detail_response.json()
    assert len(detail["items"]) == 2
    assert detail["items_total"] == "3.87"


async def test_items_total_not_required_to_match_parent_amount(
    client: AsyncClient,
) -> None:
    """Item sums differing from the parent amount are accepted, not rejected."""
    await _register_and_login(client, "sp6@example.com")
    account_id = await _create_account(client)
    category_id = await _groceries_category_id(client)
    created = await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "49.80",
            "spent_at": "2026-09-26",
        },
    )
    spent_id = created.json()["id"]

    response = await client.post(
        f"/api/v1/spents/{spent_id}/items",
        json={"name": "Milk", "amount": "2.38"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    detail = await client.get(f"/api/v1/spents/{spent_id}")
    assert detail.json()["amount"] == "49.80"
    assert detail.json()["items_total"] == "2.38"


async def test_deleting_spent_cascades_to_items(client: AsyncClient) -> None:
    """Deleting a spent also deletes its line items."""
    await _register_and_login(client, "sp7@example.com")
    account_id = await _create_account(client)
    category_id = await _groceries_category_id(client)
    created = await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "10.00",
            "spent_at": "2026-09-26",
        },
    )
    spent_id = created.json()["id"]
    item_response = await client.post(
        f"/api/v1/spents/{spent_id}/items",
        json={"name": "Milk", "amount": "2.38"},
    )
    item_id = item_response.json()["id"]

    delete_response = await client.delete(f"/api/v1/spents/{spent_id}")
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    update_response = await client.patch(
        f"/api/v1/spents/items/{item_id}", json={"amount": "1.00"}
    )
    assert update_response.status_code == status.HTTP_404_NOT_FOUND


async def test_deleting_account_with_spents_is_blocked(client: AsyncClient) -> None:
    """An account referenced by a spent can't be deleted, only archived."""
    await _register_and_login(client, "sp8@example.com")
    account_id = await _create_account(client)
    category_id = await _groceries_category_id(client)
    await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "10.00",
            "spent_at": "2026-09-26",
        },
    )

    response = await client.delete(f"/api/v1/accounts/{account_id}")

    assert response.status_code == status.HTTP_409_CONFLICT
