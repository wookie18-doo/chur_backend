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


async def test_create_and_list_account(client: AsyncClient) -> None:
    """A created account shows up in the user's own list."""
    await _register_and_login(client, "acc1@example.com")

    create_response = await client.post(
        "/api/v1/accounts",
        json={"name": "Wise EUR", "kind": "bank", "currency": "EUR", "source": "wise"},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    list_response = await client.get("/api/v1/accounts")
    names = {a["name"] for a in list_response.json()}
    assert "Wise EUR" in names


async def test_creating_account_with_market_bill_source_rejected(
    client: AsyncClient,
) -> None:
    """market_bill only ever describes an ImportJob, never an Account."""
    await _register_and_login(client, "acc2@example.com")

    response = await client.post(
        "/api/v1/accounts",
        json={
            "name": "Bad",
            "kind": "bank",
            "currency": "EUR",
            "source": "market_bill",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_archive_hides_account_and_restore_brings_it_back(
    client: AsyncClient,
) -> None:
    """Archiving removes an account from the default list; restore undoes it."""
    await _register_and_login(client, "acc3@example.com")
    created = await client.post(
        "/api/v1/accounts",
        json={"name": "Cash", "kind": "cash", "currency": "EUR"},
    )
    account_id = created.json()["id"]

    archive_response = await client.post(f"/api/v1/accounts/{account_id}/archive")
    assert archive_response.status_code == status.HTTP_200_OK
    assert archive_response.json()["is_active"] is False

    default_list = await client.get("/api/v1/accounts")
    assert account_id not in {a["id"] for a in default_list.json()}

    full_list = await client.get("/api/v1/accounts", params={"include_inactive": True})
    assert account_id in {a["id"] for a in full_list.json()}

    restore_response = await client.post(f"/api/v1/accounts/{account_id}/restore")
    assert restore_response.status_code == status.HTTP_200_OK
    assert restore_response.json()["is_active"] is True

    default_list_again = await client.get("/api/v1/accounts")
    assert account_id in {a["id"] for a in default_list_again.json()}


async def test_delete_own_empty_account(client: AsyncClient) -> None:
    """An account with no entries can be deleted outright."""
    await _register_and_login(client, "acc4@example.com")
    created = await client.post(
        "/api/v1/accounts",
        json={"name": "Cash", "kind": "cash", "currency": "EUR"},
    )
    account_id = created.json()["id"]

    response = await client.delete(f"/api/v1/accounts/{account_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_cannot_act_on_another_users_account(client: AsyncClient) -> None:
    """Archiving/deleting an account you don't own returns 404."""
    await _register_and_login(client, "acc5owner@example.com")
    created = await client.post(
        "/api/v1/accounts",
        json={"name": "Wise EUR", "kind": "bank", "currency": "EUR"},
    )
    account_id = created.json()["id"]

    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "acc5stranger@example.com")

    response = await client.post(f"/api/v1/accounts/{account_id}/archive")

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def _register_with_account(client: AsyncClient, email: str) -> tuple[str, str]:
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    created = await client.post(
        "/api/v1/accounts",
        json={"name": email, "kind": "bank", "currency": "EUR"},
    )
    return str(registered.json()["id"]), str(created.json()["id"])


async def _two_member_family(client: AsyncClient, prefix: str) -> tuple[str, str]:
    """Leave ``client`` logged in as the member; return both account ids."""
    _, owner_account = await _register_with_account(client, f"{prefix}o@example.com")
    await client.post("/api/v1/families", json={"name": "F"})
    await client.post("/api/v1/auth/logout")
    member_id, member_account = await _register_with_account(
        client, f"{prefix}m@example.com"
    )
    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/login",
        json={
            "email": f"{prefix}o@example.com",
            "password": "correct horse battery staple",
        },
    )
    await client.post("/api/v1/families/members", json={"user_id": member_id})
    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/login",
        json={
            "email": f"{prefix}m@example.com",
            "password": "correct horse battery staple",
        },
    )
    return owner_account, member_account


async def test_list_defaults_to_family_scope(client: AsyncClient) -> None:
    """Family members see each other's accounts; scope=me narrows it."""
    owner_account, member_account = await _two_member_family(client, "fam1")

    family = await client.get("/api/v1/accounts")
    me = await client.get("/api/v1/accounts", params={"scope": "me"})

    assert {a["id"] for a in family.json()} == {owner_account, member_account}
    assert {a["id"] for a in me.json()} == {member_account}


async def test_family_member_reads_balance_but_cannot_write(
    client: AsyncClient,
) -> None:
    """Balance is readable by the family; every write stays owner-only."""
    owner_account, _ = await _two_member_family(client, "fam2")

    read = await client.get(f"/api/v1/accounts/{owner_account}/balance")
    set_balance = await client.post(
        f"/api/v1/accounts/{owner_account}/balance", json={"target_balance": "1.00"}
    )
    archive = await client.post(f"/api/v1/accounts/{owner_account}/archive")

    assert read.status_code == status.HTTP_200_OK
    assert set_balance.status_code == status.HTTP_404_NOT_FOUND
    assert archive.status_code == status.HTTP_404_NOT_FOUND


async def test_stranger_sees_no_family_accounts(client: AsyncClient) -> None:
    """Someone outside the family neither lists nor reads the accounts."""
    owner_account, _ = await _two_member_family(client, "fam3")
    await client.post("/api/v1/auth/logout")
    _, stranger_account = await _register_with_account(client, "fam3s@example.com")

    listed = await client.get("/api/v1/accounts")
    read = await client.get(f"/api/v1/accounts/{owner_account}/balance")

    assert {a["id"] for a in listed.json()} == {stranger_account}
    assert read.status_code == status.HTTP_404_NOT_FOUND
