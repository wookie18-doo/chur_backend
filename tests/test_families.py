import uuid

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette import status


def _second_client(fastapi_app: FastAPI) -> AsyncClient:
    """Build another client against the same app, with its own cookie jar."""
    return AsyncClient(
        transport=ASGITransport(fastapi_app), base_url="http://test", timeout=2.0
    )


async def _register(client: AsyncClient, email: str) -> str:
    """Register a user and log them in, returning their user id."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    user_id = response.json()["id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert login.status_code == status.HTTP_200_OK
    return str(user_id)


async def test_create_family(client: AsyncClient) -> None:
    """A freshly registered user can create a family they own."""
    await _register(client, "owner1@example.com")

    response = await client.post("/api/v1/families", json={"name": "The Smiths"})

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["name"] == "The Smiths"


async def test_create_family_twice_conflicts(client: AsyncClient) -> None:
    """A user already in a family can't create (or join) a second one."""
    await _register(client, "owner2@example.com")
    await client.post("/api/v1/families", json={"name": "Family A"})

    response = await client.post("/api/v1/families", json={"name": "Family B"})

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_read_own_family_lists_the_owner(client: AsyncClient) -> None:
    """GET /families/me returns the family with the creator as its owner."""
    user_id = await _register(client, "owner3@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    response = await client.get("/api/v1/families/me")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == "The Smiths"
    assert [m["user_id"] for m in body["members"]] == [user_id]
    assert body["members"][0]["role"] == "owner"


async def test_read_own_family_not_found_when_unaffiliated(
    client: AsyncClient,
) -> None:
    """A user with no family gets 404, not an empty family."""
    await _register(client, "lonely@example.com")

    response = await client.get("/api/v1/families/me")

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_owner_can_add_and_remove_a_member(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """The owner can add another user and later remove them."""
    await _register(client, "owner4@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as other:
        other_id = await _register(other, "member4@example.com")

    add_response = await client.post(
        "/api/v1/families/members", json={"user_id": other_id}
    )
    assert add_response.status_code == status.HTTP_201_CREATED
    assert add_response.json()["role"] == "member"

    remove_response = await client.delete(f"/api/v1/families/members/{other_id}")
    assert remove_response.status_code == status.HTTP_204_NO_CONTENT


async def test_non_owner_cannot_add_members(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """A plain member can't add other members to the family."""
    await _register(client, "owner5@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as member_client:
        member_id = await _register(member_client, "member5@example.com")
        await client.post("/api/v1/families/members", json={"user_id": member_id})

        response = await member_client.post(
            "/api/v1/families/members", json={"user_id": str(uuid.uuid4())}
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_owner_cannot_leave(client: AsyncClient) -> None:
    """The owner must delete the family, not leave it."""
    owner_id = await _register(client, "owner6@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    response = await client.delete(f"/api/v1/families/members/{owner_id}")

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_member_can_leave(client: AsyncClient, fastapi_app: FastAPI) -> None:
    """A plain member can remove themselves from the family."""
    await _register(client, "owner7@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as member_client:
        member_id = await _register(member_client, "member7@example.com")
        await client.post("/api/v1/families/members", json={"user_id": member_id})

        response = await member_client.delete(f"/api/v1/families/members/{member_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_members_include_email_and_names(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """GET /families/me exposes each member's email and name."""
    await _register(client, "owner8@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as other:
        other_id = await _register(other, "member8@example.com")
    await client.post("/api/v1/families/members", json={"user_id": other_id})

    body = (await client.get("/api/v1/families/me")).json()

    assert [m["email"] for m in body["members"]] == [
        "owner8@example.com",
        "member8@example.com",
    ]
    assert body["members"][0]["role"] == "owner"


async def test_owner_can_add_member_by_email(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """Members can be added by (case-insensitive) email instead of id."""
    await _register(client, "owner9@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})
    async with _second_client(fastapi_app) as other:
        other_id = await _register(other, "member9@example.com")

    response = await client.post(
        "/api/v1/families/members", json={"email": " Member9@Example.com "}
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["user_id"] == other_id
    assert response.json()["email"] == "member9@example.com"


async def test_add_member_unknown_email_is_404(client: AsyncClient) -> None:
    """Adding an email nobody registered with is a 404, not a 500."""
    await _register(client, "owner10@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    response = await client.post(
        "/api/v1/families/members", json={"email": "nobody@example.com"}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_add_member_requires_an_identifier(client: AsyncClient) -> None:
    """Neither user_id nor email is a validation error."""
    await _register(client, "owner11@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    response = await client.post("/api/v1/families/members", json={})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_owner_can_rename_family(client: AsyncClient) -> None:
    """PATCH /families/me renames the family."""
    await _register(client, "owner12@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    response = await client.patch("/api/v1/families/me", json={"name": "The Joneses"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "The Joneses"
    assert (await client.get("/api/v1/families/me")).json()["name"] == "The Joneses"


async def test_non_owner_cannot_rename_family(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """Only the owner may rename; outsiders get 404."""
    await _register(client, "owner13@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as member_client:
        member_id = await _register(member_client, "member13@example.com")
        await client.post("/api/v1/families/members", json={"user_id": member_id})
        as_member = await member_client.patch("/api/v1/families/me", json={"name": "X"})

    async with _second_client(fastapi_app) as stranger:
        await _register(stranger, "stranger13@example.com")
        as_stranger = await stranger.patch("/api/v1/families/me", json={"name": "X"})

    assert as_member.status_code == status.HTTP_403_FORBIDDEN
    assert as_stranger.status_code == status.HTTP_404_NOT_FOUND


async def test_owner_can_transfer_ownership_then_leave(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """Promoting a member to owner demotes the actor, who may then leave."""
    owner_id = await _register(client, "owner20@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as other:
        member_id = await _register(other, "member20@example.com")
        await client.post("/api/v1/families/members", json={"user_id": member_id})

        response = await client.patch(
            f"/api/v1/families/members/{member_id}", json={"role": "owner"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "owner"

        leave = await client.delete(f"/api/v1/families/members/{owner_id}")
        assert leave.status_code == status.HTTP_204_NO_CONTENT


async def test_owner_cannot_demote_themselves(client: AsyncClient) -> None:
    """Ownership is only ever handed over, never dropped."""
    owner_id = await _register(client, "owner21@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    response = await client.patch(
        f"/api/v1/families/members/{owner_id}", json={"role": "member"}
    )

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_member_cannot_change_roles(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """Only the owner can change roles."""
    owner_id = await _register(client, "owner22@example.com")
    await client.post("/api/v1/families", json={"name": "The Smiths"})

    async with _second_client(fastapi_app) as other:
        member_id = await _register(other, "member22@example.com")
        await client.post("/api/v1/families/members", json={"user_id": member_id})

        response = await other.patch(
            f"/api/v1/families/members/{owner_id}", json={"role": "member"}
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
