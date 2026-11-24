from decimal import Decimal

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette import status


async def _register_and_login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return str(response.json()["id"])


async def _account(client: AsyncClient, **fields: object) -> str:
    body = {"name": "Wise", "kind": "bank", "currency": "EUR", **fields}
    response = await client.post("/api/v1/accounts", json=body)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return str(response.json()["id"])


async def _balance(client: AsyncClient, account_id: str) -> str:
    response = await client.get(f"/api/v1/accounts/{account_id}/balance")
    assert response.status_code == status.HTTP_200_OK
    return str(response.json()["current_balance"])


async def _category(client: AsyncClient, kind: str) -> int:
    response = await client.get("/api/v1/categories", params={"kind": kind})
    return int(response.json()[0]["id"])


def _other(fastapi_app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(fastapi_app), base_url="http://test", timeout=2.0
    )


async def test_balance_combines_every_source(client: AsyncClient) -> None:
    """Balance = opening + incomes - spents + transfers in/out + adjustments."""
    await _register_and_login(client, "bal1@example.com")
    main = await _account(client, opening_balance="100.00")
    jar = await _account(client, name="Jar", kind="jar")
    await client.post(
        "/api/v1/incomes",
        json={
            "account_id": main,
            "category_id": await _category(client, "income"),
            "amount": "50.00",
            "received_at": "2026-10-01",
        },
    )
    await client.post(
        "/api/v1/spents",
        json={
            "account_id": main,
            "category_id": await _category(client, "expense"),
            "amount": "30.00",
            "spent_at": "2026-10-02",
        },
    )
    await client.post(
        "/api/v1/transfers",
        json={
            "from_account_id": main,
            "to_account_id": jar,
            "amount": "20.00",
            "transferred_at": "2026-10-03",
        },
    )

    assert await _balance(client, main) == "100.00"
    assert await _balance(client, jar) == "20.00"


async def test_set_balance_hits_the_target_exactly(client: AsyncClient) -> None:
    """Setting a balance records an adjustment so the next read equals it."""
    await _register_and_login(client, "bal2@example.com")
    account = await _account(client, opening_balance="10.00")

    first = await client.post(
        f"/api/v1/accounts/{account}/balance",
        json={"target_balance": "500.00", "reason": "Existing savings"},
    )
    assert first.status_code == status.HTTP_201_CREATED
    assert first.json()["delta"] == "490.00"
    assert await _balance(client, account) == "500.00"

    await client.post(
        f"/api/v1/accounts/{account}/balance", json={"target_balance": "420.50"}
    )
    assert await _balance(client, account) == "420.50"


async def test_balance_is_owner_only(client: AsyncClient) -> None:
    """Another user can neither read nor set an account's balance."""
    await _register_and_login(client, "bal3@example.com")
    account = await _account(client)
    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "bal4@example.com")

    read = await client.get(f"/api/v1/accounts/{account}/balance")
    write = await client.post(
        f"/api/v1/accounts/{account}/balance", json={"target_balance": "1.00"}
    )

    assert read.status_code == status.HTTP_404_NOT_FOUND
    assert write.status_code == status.HTTP_404_NOT_FOUND


async def test_transfer_never_counts_as_spend_or_income(client: AsyncClient) -> None:
    """Transfers stay out of the report's income/spend totals."""
    await _register_and_login(client, "tr1@example.com")
    main = await _account(client)
    savings = await _account(client, name="Safety", kind="jar", is_savings=True)
    other = await _account(client, name="Other", kind="jar")
    for target, amount in ((savings, "40.00"), (other, "15.00")):
        response = await client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": main,
                "to_account_id": target,
                "amount": amount,
                "transferred_at": "2026-10-03",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["to_amount"] == amount

    report = (await client.get("/api/v1/reports/summary")).json()

    assert Decimal(report["total_income"]) == 0
    assert Decimal(report["total_spent"]) == 0
    assert Decimal(report["total_transferred_to_savings"]) == Decimal("40.00")


async def test_cross_currency_transfer_needs_to_amount(client: AsyncClient) -> None:
    """Different currencies must state what arrived; it's never auto-converted."""
    await _register_and_login(client, "tr2@example.com")
    eur = await _account(client)
    usd = await _account(client, name="USD", currency="USD")
    payload = {
        "from_account_id": eur,
        "to_account_id": usd,
        "amount": "100.00",
        "transferred_at": "2026-10-03",
    }

    missing = await client.post("/api/v1/transfers", json=payload)
    given = await client.post(
        "/api/v1/transfers", json={**payload, "to_amount": "108.00"}
    )

    assert missing.status_code == status.HTTP_400_BAD_REQUEST
    assert given.status_code == status.HTTP_201_CREATED
    assert await _balance(client, usd) == "108.00"
    assert await _balance(client, eur) == "-100.00"


async def test_transfer_to_family_member_ok_but_stranger_rejected(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """The destination must be in the actor's household."""
    await _register_and_login(client, "tr3@example.com")
    mine = await _account(client)
    await client.post("/api/v1/families", json={"name": "F"})

    async with _other(fastapi_app) as partner:
        partner_id = await _register_and_login(partner, "tr4@example.com")
        partner_account = await _account(partner)
    async with _other(fastapi_app) as stranger:
        await _register_and_login(stranger, "tr5@example.com")
        stranger_account = await _account(stranger)

    await client.post("/api/v1/families/members", json={"user_id": partner_id})
    base = {"from_account_id": mine, "amount": "5.00", "transferred_at": "2026-10-03"}

    ok = await client.post(
        "/api/v1/transfers", json={**base, "to_account_id": partner_account}
    )
    bad = await client.post(
        "/api/v1/transfers", json={**base, "to_account_id": stranger_account}
    )
    same = await client.post("/api/v1/transfers", json={**base, "to_account_id": mine})

    assert ok.status_code == status.HTTP_201_CREATED
    assert bad.status_code == status.HTTP_400_BAD_REQUEST
    assert same.status_code == status.HTTP_400_BAD_REQUEST


async def test_transfer_source_must_be_own(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """You can't move money out of someone else's account."""
    await _register_and_login(client, "tr6@example.com")
    mine = await _account(client)
    async with _other(fastapi_app) as other:
        await _register_and_login(other, "tr7@example.com")
        theirs = await _account(other)

    response = await client.post(
        "/api/v1/transfers",
        json={
            "from_account_id": theirs,
            "to_account_id": mine,
            "amount": "5.00",
            "transferred_at": "2026-10-03",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_transfer_list_update_delete_and_visibility(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """CRUD, with private transfers hidden from family members."""
    await _register_and_login(client, "tr8@example.com")
    main = await _account(client)
    jar = await _account(client, name="Jar", kind="jar")
    await client.post("/api/v1/families", json={"name": "F"})
    created = (
        await client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": main,
                "to_account_id": jar,
                "amount": "10.00",
                "transferred_at": "2026-10-03",
            },
        )
    ).json()

    updated = await client.patch(
        f"/api/v1/transfers/{created['id']}",
        json={"amount": "12.00", "visibility": "family"},
    )
    listed = await client.get("/api/v1/transfers", params={"date_from": "2026-10-01"})

    assert updated.json()["amount"] == "12.00"
    assert updated.json()["to_amount"] == "12.00"
    assert [t["id"] for t in listed.json()] == [created["id"]]
    assert await _balance(client, jar) == "12.00"

    private = (
        await client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": main,
                "to_account_id": jar,
                "amount": "1.00",
                "transferred_at": "2026-10-04",
            },
        )
    ).json()
    async with _other(fastapi_app) as partner:
        partner_id = await _register_and_login(partner, "tr9@example.com")
        await client.post("/api/v1/families/members", json={"user_id": partner_id})
        seen = await partner.get("/api/v1/transfers", params={"scope": "family"})
        hidden = await partner.get(f"/api/v1/transfers/{private['id']}")
        shared = await partner.get(f"/api/v1/transfers/{created['id']}")

    assert [t["id"] for t in seen.json()] == [created["id"]]
    assert hidden.status_code == status.HTTP_404_NOT_FOUND
    assert shared.status_code == status.HTTP_200_OK

    deleted = await client.delete(f"/api/v1/transfers/{created['id']}")
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert await _balance(client, jar) == "1.00"
