from httpx import AsyncClient
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette import status

_PASSWORD = "correct horse battery staple"  # noqa: S105


async def _login(client: AsyncClient, email: str) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD}
    )
    await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )


async def test_list_and_retrieve(client: AsyncClient) -> None:
    """Any logged-in user sees the seeded sources, including market_bill."""
    await _login(client, "ss1@example.com")

    listed = await client.get("/api/v1/statement-sources")
    first = listed.json()[0]
    fetched = await client.get(f"/api/v1/statement-sources/{first['id']}")

    assert listed.status_code == status.HTTP_200_OK
    assert "market_bill" in {s["code"] for s in listed.json()}
    assert fetched.json() == first


async def test_retrieve_missing_is_404(client: AsyncClient) -> None:
    """An unknown id is a 404."""
    await _login(client, "ss2@example.com")

    response = await client.get("/api/v1/statement-sources/999999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_requires_auth(client: AsyncClient) -> None:
    """Anonymous callers are rejected."""
    response = await client.get("/api/v1/statement-sources")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_create_requires_superuser(client: AsyncClient) -> None:
    """A regular user can't create sources."""
    await _login(client, "ss3@example.com")

    response = await client.post("/api/v1/statement-sources", json={"name": "Nope"})

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_superuser_creates_source(
    client: AsyncClient, dbsession: AsyncSession
) -> None:
    """A superuser creates a source; duplicates and non-latin names fail."""
    await _login(client, "ss4@example.com")
    await dbsession.execute(
        text("UPDATE \"user\" SET is_superuser = true WHERE email = 'ss4@example.com'")
    )

    created = await client.post(
        "/api/v1/statement-sources", json={"name": "Trade Republic"}
    )
    duplicate = await client.post(
        "/api/v1/statement-sources", json={"name": "Trade Republic"}
    )
    non_latin = await client.post(
        "/api/v1/statement-sources", json={"name": "\u0411\u0430\u043d\u043a"}
    )

    assert created.status_code == status.HTTP_201_CREATED
    assert created.json()["code"] == "trade_republic"
    assert duplicate.status_code == status.HTTP_409_CONFLICT
    assert non_latin.status_code == status.HTTP_400_BAD_REQUEST
