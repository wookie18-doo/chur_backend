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


async def _housing_category_id(client: AsyncClient) -> int:
    response = await client.get("/api/v1/categories", params={"kind": "expense"})
    category_id: int = next(c["id"] for c in response.json() if c["name"] == "Housing")
    return category_id


async def test_create_wishlist_and_add_item(client: AsyncClient) -> None:
    """A created wishlist item shows up in the wishlist's item list."""
    await _register_and_login(client, "wl1@example.com")
    category_id = await _housing_category_id(client)
    wishlist = await client.post(
        "/api/v1/wishlists",
        json={"name": "Autumn home refresh", "date_from": "2026-10-01"},
    )
    wishlist_id = wishlist.json()["id"]

    item_response = await client.post(
        f"/api/v1/wishlists/{wishlist_id}/items",
        json={"category_id": category_id, "name": "Floor lamp", "amount": "180.00"},
    )
    assert item_response.status_code == status.HTTP_201_CREATED
    assert item_response.json()["status"] == "planned"

    items = await client.get(f"/api/v1/wishlists/{wishlist_id}/items")
    names = {i["name"] for i in items.json()}
    assert "Floor lamp" in names


async def test_transfer_item_between_own_wishlists(client: AsyncClient) -> None:
    """An item moves to another wishlist the same owner controls."""
    await _register_and_login(client, "wl2@example.com")
    category_id = await _housing_category_id(client)
    list_a = (await client.post("/api/v1/wishlists", json={"name": "List A"})).json()
    list_b = (await client.post("/api/v1/wishlists", json={"name": "List B"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{list_a['id']}/items",
            json={"category_id": category_id, "name": "Rug", "amount": "50.00"},
        )
    ).json()

    response = await client.post(
        f"/api/v1/wishlists/items/{item['id']}/transfer",
        json={"target_wishlist_id": list_b["id"]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["wishlist_id"] == list_b["id"]
    assert response.json()["status"] == "planned"


async def test_transfer_item_to_foreign_wishlist_rejected(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """An item can't be transferred to a wishlist owned by someone else."""
    await _register_and_login(client, "wl3@example.com")
    category_id = await _housing_category_id(client)
    own_list = (await client.post("/api/v1/wishlists", json={"name": "Mine"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{own_list['id']}/items",
            json={"category_id": category_id, "name": "Rug", "amount": "50.00"},
        )
    ).json()

    async with _second_client(fastapi_app) as stranger:
        await _register_and_login(stranger, "wl3stranger@example.com")
        foreign_list = (
            await stranger.post("/api/v1/wishlists", json={"name": "Theirs"})
        ).json()

        response = await client.post(
            f"/api/v1/wishlists/items/{item['id']}/transfer",
            json={"target_wishlist_id": foreign_list["id"]},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_realise_by_creating_new_spent(client: AsyncClient) -> None:
    """Realising without existing_spent_id creates and links a new spent."""
    await _register_and_login(client, "wl4@example.com")
    account_id = await _create_account(client)
    category_id = await _housing_category_id(client)
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "List"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{wishlist['id']}/items",
            json={"category_id": category_id, "name": "Rug", "amount": "50.00"},
        )
    ).json()

    response = await client.post(
        f"/api/v1/wishlists/items/{item['id']}/realise",
        json={"account_id": account_id},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "realised"
    assert body["realised_spent_id"] is not None

    spent = await client.get(f"/api/v1/spents/{body['realised_spent_id']}")
    assert spent.json()["amount"] == "50.00"


async def test_realise_without_account_id_fails(client: AsyncClient) -> None:
    """Creating a new spent from an item requires an explicit account_id."""
    await _register_and_login(client, "wl5@example.com")
    category_id = await _housing_category_id(client)
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "List"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{wishlist['id']}/items",
            json={"category_id": category_id, "name": "Rug", "amount": "50.00"},
        )
    ).json()

    response = await client.post(
        f"/api/v1/wishlists/items/{item['id']}/realise", json={}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_realise_by_merging_existing_spent(client: AsyncClient) -> None:
    """Realising with existing_spent_id links to an already-recorded spent."""
    await _register_and_login(client, "wl6@example.com")
    account_id = await _create_account(client)
    category_id = await _housing_category_id(client)
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "List"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{wishlist['id']}/items",
            json={"category_id": category_id, "name": "Rug", "amount": "184.50"},
        )
    ).json()
    spent = (
        await client.post(
            "/api/v1/spents",
            json={
                "account_id": account_id,
                "category_id": category_id,
                "amount": "184.50",
                "spent_at": "2026-09-20",
            },
        )
    ).json()

    response = await client.post(
        f"/api/v1/wishlists/items/{item['id']}/realise",
        json={"existing_spent_id": spent["id"]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["realised_spent_id"] == spent["id"]

    spent_detail = await client.get(f"/api/v1/spents/{spent['id']}")
    assert spent_detail.json()["id"] == spent["id"]


async def test_candidates_lists_unlinked_same_category_spents(
    client: AsyncClient,
) -> None:
    """Candidates only include the actor's own, unlinked, same-category spents."""
    await _register_and_login(client, "wl7@example.com")
    account_id = await _create_account(client)
    category_id = await _housing_category_id(client)
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "List"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{wishlist['id']}/items",
            json={"category_id": category_id, "name": "Rug", "amount": "180.00"},
        )
    ).json()
    matching_spent = (
        await client.post(
            "/api/v1/spents",
            json={
                "account_id": account_id,
                "category_id": category_id,
                "amount": "179.00",
                "spent_at": "2026-09-25",
            },
        )
    ).json()

    response = await client.get(f"/api/v1/wishlists/items/{item['id']}/candidates")

    assert response.status_code == status.HTTP_200_OK
    candidate_ids = {c["id"] for c in response.json()}
    assert matching_spent["id"] in candidate_ids


async def test_family_member_cannot_see_item_hidden_from_family(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """An item overridden to PRIVATE stays hidden even on a FAMILY wishlist."""
    await _register_and_login(client, "wl8owner@example.com")
    category_id = await _housing_category_id(client)
    await client.post("/api/v1/families", json={"name": "The Smiths"})
    wishlist = (
        await client.post(
            "/api/v1/wishlists", json={"name": "Shared list", "visibility": "family"}
        )
    ).json()
    await client.post(
        f"/api/v1/wishlists/{wishlist['id']}/items",
        json={"category_id": category_id, "name": "Visible item", "amount": "10.00"},
    )
    await client.post(
        f"/api/v1/wishlists/{wishlist['id']}/items",
        json={
            "category_id": category_id,
            "name": "Secret item",
            "amount": "20.00",
            "visibility": "private",
        },
    )

    async with _second_client(fastapi_app) as member:
        await _register_and_login(member, "wl8member@example.com")
        member_user_id = (await member.get("/api/v1/users/me")).json()["id"]
        await client.post("/api/v1/families/members", json={"user_id": member_user_id})

        response = await member.get(f"/api/v1/wishlists/{wishlist['id']}/items")

    names = {i["name"] for i in response.json()}
    assert names == {"Visible item"}


async def test_deleting_wishlist_cascades_to_items(client: AsyncClient) -> None:
    """Deleting a wishlist deletes its items too."""
    await _register_and_login(client, "wl9@example.com")
    category_id = await _housing_category_id(client)
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "List"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{wishlist['id']}/items",
            json={"category_id": category_id, "name": "Rug", "amount": "50.00"},
        )
    ).json()

    delete_response = await client.delete(f"/api/v1/wishlists/{wishlist['id']}")
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    update_response = await client.patch(
        f"/api/v1/wishlists/items/{item['id']}", json={"amount": "1.00"}
    )
    assert update_response.status_code == status.HTTP_404_NOT_FOUND


async def test_repeating_item_rolls_window_on_realise(client: AsyncClient) -> None:
    """Realising a yearly item posts one spent and moves to next year."""
    await _register_and_login(client, "wl_rep1@example.com")
    account_id = await _create_account(client)
    category_id = await _housing_category_id(client)
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "List"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{wishlist['id']}/items",
            json={
                "category_id": category_id,
                "name": "Car insurance",
                "amount": "400.00",
                "planned_date": "2026-03-01",
                "planned_date_to": "2026-03-15",
                "repeat": True,
                "frequency": "yearly",
            },
        )
    ).json()

    response = await client.post(
        f"/api/v1/wishlists/items/{item['id']}/realise",
        json={"account_id": account_id, "spent_at": "2026-03-10"},
    )

    body = response.json()
    assert body["status"] == "planned"
    assert body["planned_date"] == "2027-03-01"
    assert body["planned_date_to"] == "2027-03-15"
    spent = await client.get(f"/api/v1/spents/{body['realised_spent_id']}")
    assert spent.json()["spent_at"] == "2026-03-10"


async def test_repeating_item_closes_after_repeat_until(client: AsyncClient) -> None:
    """With no next window left inside repeat_until the item is REALISED."""
    await _register_and_login(client, "wl_rep2@example.com")
    account_id = await _create_account(client)
    category_id = await _housing_category_id(client)
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "List"})).json()
    item = (
        await client.post(
            f"/api/v1/wishlists/{wishlist['id']}/items",
            json={
                "category_id": category_id,
                "name": "Tax",
                "amount": "50.00",
                "planned_date": "2026-03-01",
                "repeat": True,
                "frequency": "weekly",
                "repeat_until": "2026-03-07",
            },
        )
    ).json()

    response = await client.post(
        f"/api/v1/wishlists/items/{item['id']}/realise",
        json={"account_id": account_id},
    )

    assert response.json()["status"] == "realised"
    assert response.json()["planned_date"] == "2026-03-01"
