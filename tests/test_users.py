from httpx import AsyncClient
from starlette import status

PASSWORD = "correct horse battery staple"  # noqa: S105


async def _register_and_login(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == status.HTTP_201_CREATED
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == status.HTTP_200_OK


async def test_delete_current_user_requires_auth(client: AsyncClient) -> None:
    """Anonymous requests can't delete anything."""
    response = await client.delete("/api/v1/users/me")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_delete_current_user(client: AsyncClient) -> None:
    """Deleting removes the user and their data, and ends the session."""
    await _register_and_login(client, "gone@example.com")
    family = await client.post("/api/v1/families", json={"name": "Solo"})
    assert family.status_code == status.HTTP_201_CREATED

    response = await client.delete("/api/v1/users/me")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert (await client.get("/api/v1/users/me")).status_code == (
        status.HTTP_401_UNAUTHORIZED
    )
    relogin = await client.post(
        "/api/v1/auth/login",
        json={"email": "gone@example.com", "password": PASSWORD},
    )
    assert relogin.status_code == status.HTTP_401_UNAUTHORIZED


async def test_delete_account_page(client: AsyncClient) -> None:
    """The web deletion page is public."""
    response = await client.get("/delete-account")

    assert response.status_code == status.HTTP_200_OK
    assert "Delete account" in response.text


async def test_update_current_user(client: AsyncClient) -> None:
    """PATCH /users/me changes only the fields sent."""
    await _register_and_login(client, "edit@example.com")

    response = await client.patch(
        "/api/v1/users/me", json={"first_name": "Ann", "username": "ann"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["first_name"] == "Ann"
    assert response.json()["username"] == "ann"
    assert response.json()["email"] == "edit@example.com"


async def test_update_current_user_conflict(client: AsyncClient) -> None:
    """A username already taken by someone else is a 409."""
    await _register_and_login(client, "first@example.com")
    await client.patch("/api/v1/users/me", json={"username": "taken"})
    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "second@example.com")

    response = await client.patch("/api/v1/users/me", json={"username": "taken"})

    assert response.status_code == status.HTTP_409_CONFLICT
