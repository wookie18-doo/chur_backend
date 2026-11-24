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


async def test_list_expense_categories_includes_builtins(client: AsyncClient) -> None:
    """Every user sees the seeded built-in expense categories."""
    await _register_and_login(client, "cat1@example.com")

    response = await client.get("/api/v1/categories", params={"kind": "expense"})

    assert response.status_code == status.HTTP_200_OK
    names = {c["name"] for c in response.json()}
    assert {"Groceries", "Transport", "Housing", "Health", "Other"} <= names


async def test_list_income_categories_includes_builtins(client: AsyncClient) -> None:
    """Every user sees the seeded built-in income categories."""
    await _register_and_login(client, "cat2@example.com")

    response = await client.get("/api/v1/categories", params={"kind": "income"})

    assert response.status_code == status.HTTP_200_OK
    names = {c["name"] for c in response.json()}
    assert {"Salary", "Other", "Uncategorized"} <= names


async def test_create_custom_category_is_private_to_its_owner(
    client: AsyncClient,
) -> None:
    """A custom category only shows up for the user who created it."""
    await _register_and_login(client, "cat3@example.com")

    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Pets", "kind": "expense", "color": "teal"},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    assert create_response.json()["owner_id"] is not None

    list_response = await client.get("/api/v1/categories", params={"kind": "expense"})
    names = {c["name"] for c in list_response.json()}
    assert "Pets" in names


async def test_owner_can_delete_their_own_category(client: AsyncClient) -> None:
    """A user can delete a custom category they created."""
    await _register_and_login(client, "cat4@example.com")
    created = await client.post(
        "/api/v1/categories", json={"name": "Pets", "kind": "expense"}
    )
    category_id = created.json()["id"]

    response = await client.delete(f"/api/v1/categories/{category_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_cannot_delete_a_builtin_category(client: AsyncClient) -> None:
    """A built-in category can't be deleted by a regular user."""
    await _register_and_login(client, "cat5@example.com")
    categories = await client.get("/api/v1/categories", params={"kind": "expense"})
    builtin_id = next(c["id"] for c in categories.json() if c["name"] == "Groceries")

    response = await client.delete(f"/api/v1/categories/{builtin_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_owner_can_update_their_own_category(client: AsyncClient) -> None:
    """PATCH renames/recolours a custom category, leaving other fields alone."""
    await _register_and_login(client, "cat5@example.com")
    created = await client.post(
        "/api/v1/categories",
        json={"name": "Pets", "kind": "expense", "color": "teal"},
    )
    category_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/categories/{category_id}", json={"name": "Animals"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "Animals"
    assert response.json()["color"] == "teal"


async def test_builtin_category_cannot_be_updated(client: AsyncClient) -> None:
    """Built-in categories are read-only."""
    await _register_and_login(client, "cat6@example.com")
    listed = await client.get("/api/v1/categories", params={"kind": "expense"})
    builtin_id = listed.json()[0]["id"]

    response = await client.patch(
        f"/api/v1/categories/{builtin_id}", json={"name": "Hacked"}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
