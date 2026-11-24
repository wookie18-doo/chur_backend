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


async def _other_income_category_id(client: AsyncClient) -> int:
    response = await client.get("/api/v1/categories", params={"kind": "income"})
    category_id: int = next(c["id"] for c in response.json() if c["name"] == "Other")
    return category_id


async def test_create_and_list_planned_income(client: AsyncClient) -> None:
    """A created planned income shows up in the user's own list."""
    await _register_and_login(client, "pi1@example.com")
    category_id = await _other_income_category_id(client)

    create_response = await client.post(
        "/api/v1/planned-incomes",
        json={
            "name": "Tax refund 2025",
            "category_id": category_id,
            "amount": "640.00",
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    assert create_response.json()["status"] == "planned"

    list_response = await client.get("/api/v1/planned-incomes")
    names = {p["name"] for p in list_response.json()}
    assert "Tax refund 2025" in names


async def test_realise_by_creating_new_income(client: AsyncClient) -> None:
    """Realising without existing_income_id creates and links a new income."""
    await _register_and_login(client, "pi2@example.com")
    account_id = await _create_account(client)
    category_id = await _other_income_category_id(client)
    planned = (
        await client.post(
            "/api/v1/planned-incomes",
            json={"name": "Tax refund", "category_id": category_id, "amount": "640.00"},
        )
    ).json()

    response = await client.post(
        f"/api/v1/planned-incomes/{planned['id']}/realise",
        json={"account_id": account_id},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "realised"
    assert body["realised_income_id"] is not None


async def test_realise_without_account_id_fails(client: AsyncClient) -> None:
    """Creating a new income from a planned one requires an account_id."""
    await _register_and_login(client, "pi3@example.com")
    category_id = await _other_income_category_id(client)
    planned = (
        await client.post(
            "/api/v1/planned-incomes",
            json={"name": "Tax refund", "category_id": category_id, "amount": "640.00"},
        )
    ).json()

    response = await client.post(
        f"/api/v1/planned-incomes/{planned['id']}/realise", json={}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_realise_by_merging_existing_income(client: AsyncClient) -> None:
    """Realising with existing_income_id links to an already-recorded income."""
    await _register_and_login(client, "pi4@example.com")
    account_id = await _create_account(client)
    category_id = await _other_income_category_id(client)
    planned = (
        await client.post(
            "/api/v1/planned-incomes",
            json={"name": "Freelance", "category_id": category_id, "amount": "850.00"},
        )
    ).json()
    income = (
        await client.post(
            "/api/v1/incomes",
            json={
                "account_id": account_id,
                "category_id": category_id,
                "amount": "850.00",
                "received_at": "2026-09-24",
            },
        )
    ).json()

    response = await client.post(
        f"/api/v1/planned-incomes/{planned['id']}/realise",
        json={"existing_income_id": income["id"]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["realised_income_id"] == income["id"]


async def test_candidates_excludes_already_linked_income(client: AsyncClient) -> None:
    """Once an income is claimed by a planned income, it drops off candidates."""
    await _register_and_login(client, "pi5@example.com")
    account_id = await _create_account(client)
    category_id = await _other_income_category_id(client)
    planned_a = (
        await client.post(
            "/api/v1/planned-incomes",
            json={"name": "A", "category_id": category_id, "amount": "100.00"},
        )
    ).json()
    planned_b = (
        await client.post(
            "/api/v1/planned-incomes",
            json={"name": "B", "category_id": category_id, "amount": "100.00"},
        )
    ).json()
    income = (
        await client.post(
            "/api/v1/incomes",
            json={
                "account_id": account_id,
                "category_id": category_id,
                "amount": "100.00",
                "received_at": "2026-09-24",
            },
        )
    ).json()

    before = await client.get(f"/api/v1/planned-incomes/{planned_a['id']}/candidates")
    assert income["id"] in {c["id"] for c in before.json()}

    await client.post(
        f"/api/v1/planned-incomes/{planned_a['id']}/realise",
        json={"existing_income_id": income["id"]},
    )

    after = await client.get(f"/api/v1/planned-incomes/{planned_b['id']}/candidates")
    assert income["id"] not in {c["id"] for c in after.json()}


async def test_delete_own_planned_income(client: AsyncClient) -> None:
    """An owner can delete their own planned income."""
    await _register_and_login(client, "pi6@example.com")
    category_id = await _other_income_category_id(client)
    planned = (
        await client.post(
            "/api/v1/planned-incomes",
            json={"name": "Gift", "category_id": category_id, "amount": "50.00"},
        )
    ).json()

    response = await client.delete(f"/api/v1/planned-incomes/{planned['id']}")

    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_repeating_income_rolls_window_on_realise(client: AsyncClient) -> None:
    """Realising a monthly income posts one income and moves the window."""
    await _register_and_login(client, "pi_rep1@example.com")
    account_id = await _create_account(client)
    category_id = await _other_income_category_id(client)
    planned = (
        await client.post(
            "/api/v1/planned-incomes",
            json={
                "name": "Salary",
                "category_id": category_id,
                "amount": "3000.00",
                "date_from": "2026-01-31",
                "date_to": "2026-02-04",
                "repeat": True,
                "frequency": "monthly",
            },
        )
    ).json()

    first = await client.post(
        f"/api/v1/planned-incomes/{planned['id']}/realise",
        json={"account_id": account_id, "received_at": "2026-02-02"},
    )
    second = await client.post(
        f"/api/v1/planned-incomes/{planned['id']}/realise",
        json={"account_id": account_id},
    )

    assert first.json()["status"] == "planned"
    assert first.json()["date_from"] == "2026-02-28"
    assert first.json()["date_to"] == "2026-03-04"
    # The 31st anchor is restored after February's clamp.
    assert second.json()["date_from"] == "2026-03-31"
    assert first.json()["realised_income_id"] is not None


async def test_repeating_income_closes_after_repeat_until(client: AsyncClient) -> None:
    """The last occurrence before repeat_until ends in REALISED."""
    await _register_and_login(client, "pi_rep2@example.com")
    account_id = await _create_account(client)
    category_id = await _other_income_category_id(client)
    planned = (
        await client.post(
            "/api/v1/planned-incomes",
            json={
                "name": "Dividend",
                "category_id": category_id,
                "amount": "100.00",
                "date_from": "2026-01-10",
                "repeat": True,
                "frequency": "yearly",
                "repeat_until": "2026-12-31",
            },
        )
    ).json()

    response = await client.post(
        f"/api/v1/planned-incomes/{planned['id']}/realise",
        json={"account_id": account_id},
    )

    assert response.json()["status"] == "realised"
    assert response.json()["date_from"] == "2026-01-10"


async def test_repeat_without_date_or_daily_rejected(client: AsyncClient) -> None:
    """A repeat needs a start date and can't be daily."""
    await _register_and_login(client, "pi_rep3@example.com")
    category_id = await _other_income_category_id(client)
    base = {"name": "Pay", "category_id": category_id, "amount": "1.00"}

    no_date = await client.post(
        "/api/v1/planned-incomes", json={**base, "repeat": True, "frequency": "weekly"}
    )
    daily = await client.post(
        "/api/v1/planned-incomes",
        json={**base, "date_from": "2026-01-01", "repeat": True, "frequency": "daily"},
    )

    assert no_date.status_code == status.HTTP_400_BAD_REQUEST
    assert daily.status_code == status.HTTP_400_BAD_REQUEST


async def test_repeat_flag_and_frequency_must_agree(client: AsyncClient) -> None:
    """Frequency needs repeat=true and repeat=true needs a frequency."""
    await _register_and_login(client, "pi_rep4@example.com")
    category_id = await _other_income_category_id(client)
    base = {
        "name": "Pay",
        "category_id": category_id,
        "amount": "1.00",
        "date_from": "2026-01-01",
    }

    flag_only = await client.post(
        "/api/v1/planned-incomes", json={**base, "repeat": True}
    )
    frequency_only = await client.post(
        "/api/v1/planned-incomes", json={**base, "frequency": "weekly"}
    )

    assert flag_only.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert frequency_only.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_repeat_false_clears_repeat_on_update(client: AsyncClient) -> None:
    """Patching repeat=false turns a repeating income into a one-time one."""
    await _register_and_login(client, "pi_rep5@example.com")
    category_id = await _other_income_category_id(client)
    planned = (
        await client.post(
            "/api/v1/planned-incomes",
            json={
                "name": "Pay",
                "category_id": category_id,
                "amount": "1.00",
                "date_from": "2026-01-01",
                "repeat": True,
                "frequency": "weekly",
            },
        )
    ).json()
    assert planned["repeat"] is True

    response = await client.patch(
        f"/api/v1/planned-incomes/{planned['id']}", json={"repeat": False}
    )

    assert response.json()["repeat"] is False
    assert response.json()["frequency"] is None
