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


async def _account(client: AsyncClient, **fields: object) -> dict[str, object]:
    body = {"name": "Wise", "kind": "bank", "currency": "EUR", **fields}
    response = await client.post("/api/v1/accounts", json=body)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    result: dict[str, object] = response.json()
    return result


async def test_list_currencies(client: AsyncClient) -> None:
    """The seeded active currencies are offered for account creation."""
    await _register_and_login(client, "cur1@example.com")

    response = await client.get("/api/v1/currencies")

    assert response.status_code == status.HTTP_200_OK
    assert {c["code"] for c in response.json()} >= {"EUR", "USD", "GBP", "CHF"}


async def test_currencies_require_auth(client: AsyncClient) -> None:
    """Anonymous callers are rejected."""
    response = await client.get("/api/v1/currencies")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_unsupported_currency_is_rejected(client: AsyncClient) -> None:
    """Creating or updating an account with an unknown currency is a 400."""
    await _register_and_login(client, "cur2@example.com")

    created = await client.post(
        "/api/v1/accounts",
        json={"name": "X", "kind": "cash", "currency": "XYZ"},
    )
    account = await _account(client)
    updated = await client.patch(
        f"/api/v1/accounts/{account['id']}", json={"currency": "XYZ"}
    )

    assert created.status_code == status.HTTP_400_BAD_REQUEST
    assert updated.status_code == status.HTTP_400_BAD_REQUEST


async def test_jars_nest_one_level_and_filter_by_parent(client: AsyncClient) -> None:
    """A jar sits under a bank, can't nest further, and lists by parent."""
    await _register_and_login(client, "jar1@example.com")
    wise = await _account(client, name="Wise", source="wise")
    other = await _account(client, name="bunq")
    jar = await _account(
        client, name="Sections", kind="jar", parent_account_id=wise["id"]
    )
    await _account(client, name="Other jar", kind="jar", parent_account_id=other["id"])

    nested = await client.post(
        "/api/v1/accounts",
        json={
            "name": "Jar of jar",
            "kind": "jar",
            "currency": "EUR",
            "parent_account_id": jar["id"],
        },
    )
    children = await client.get(
        "/api/v1/accounts", params={"parent_account_id": str(wise["id"])}
    )

    assert jar["parent_account_id"] == wise["id"]
    assert nested.status_code == status.HTTP_400_BAD_REQUEST
    assert [a["id"] for a in children.json()] == [jar["id"]]


async def test_jar_cannot_have_import_source(client: AsyncClient) -> None:
    """A jar/card can't be fed by a statement import."""
    await _register_and_login(client, "jar2@example.com")
    wise = await _account(client)

    response = await client.post(
        "/api/v1/accounts",
        json={
            "name": "Jar",
            "kind": "jar",
            "currency": "EUR",
            "source": "wise",
            "parent_account_id": wise["id"],
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_parent_must_be_own_account(client: AsyncClient) -> None:
    """A jar can't hang off someone else's (or a missing) account."""
    await _register_and_login(client, "jar3@example.com")
    mine = await _account(client)
    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "jar4@example.com")

    response = await client.post(
        "/api/v1/accounts",
        json={
            "name": "Jar",
            "kind": "jar",
            "currency": "EUR",
            "parent_account_id": mine["id"],
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_root_with_jars_cannot_become_a_jar(client: AsyncClient) -> None:
    """Re-parenting an account that already has jars would nest two levels."""
    await _register_and_login(client, "jar5@example.com")
    wise = await _account(client)
    bunq = await _account(client, name="bunq")
    await _account(client, name="Jar", kind="jar", parent_account_id=wise["id"])

    response = await client.patch(
        f"/api/v1/accounts/{wise['id']}", json={"parent_account_id": bunq["id"]}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_deleting_root_cascades_to_jars(client: AsyncClient) -> None:
    """Deleting a bank deletes its jars with it."""
    await _register_and_login(client, "jar6@example.com")
    wise = await _account(client)
    await _account(client, name="Jar", kind="jar", parent_account_id=wise["id"])

    deleted = await client.delete(f"/api/v1/accounts/{wise['id']}")
    remaining = await client.get("/api/v1/accounts", params={"include_inactive": True})

    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert remaining.json() == []


async def test_realising_wishlist_item_uses_planned_account(
    client: AsyncClient,
) -> None:
    """An item planned against a jar realises without naming an account."""
    await _register_and_login(client, "jar7@example.com")
    wise = await _account(client)
    jar = await _account(client, name="Jar", kind="jar", parent_account_id=wise["id"])
    categories = (
        await client.get("/api/v1/categories", params={"kind": "expense"})
    ).json()
    wishlist = (await client.post("/api/v1/wishlists", json={"name": "L"})).json()

    item = await client.post(
        f"/api/v1/wishlists/{wishlist['id']}/items",
        json={
            "category_id": categories[0]["id"],
            "name": "Sections",
            "amount": "75.00",
            "account_id": jar["id"],
        },
    )
    realised = await client.post(
        f"/api/v1/wishlists/items/{item.json()['id']}/realise", json={}
    )

    assert item.json()["account_id"] == jar["id"]
    assert realised.status_code == status.HTTP_200_OK
    spents = (await client.get("/api/v1/spents")).json()
    assert [(s["account_id"], s["amount"]) for s in spents] == [(jar["id"], "75.00")]


async def test_plan_account_must_be_own(client: AsyncClient) -> None:
    """Planning against an account you don't own is a 400."""
    await _register_and_login(client, "jar8@example.com")
    mine = await _account(client)
    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "jar9@example.com")
    categories = (
        await client.get("/api/v1/categories", params={"kind": "income"})
    ).json()

    response = await client.post(
        "/api/v1/planned-incomes",
        json={
            "name": "Salary",
            "category_id": categories[0]["id"],
            "amount": "10.00",
            "account_id": mine["id"],
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_realising_planned_income_uses_planned_account(
    client: AsyncClient,
) -> None:
    """A planned income with an account realises without overrides."""
    await _register_and_login(client, "jar10@example.com")
    wise = await _account(client)
    categories = (
        await client.get("/api/v1/categories", params={"kind": "income"})
    ).json()
    planned = await client.post(
        "/api/v1/planned-incomes",
        json={
            "name": "Salary",
            "category_id": categories[0]["id"],
            "amount": "10.00",
            "account_id": wise["id"],
        },
    )

    realised = await client.post(
        f"/api/v1/planned-incomes/{planned.json()['id']}/realise", json={}
    )

    assert realised.status_code == status.HTTP_200_OK
    incomes = (await client.get("/api/v1/incomes")).json()
    assert [i["account_id"] for i in incomes] == [wise["id"]]
