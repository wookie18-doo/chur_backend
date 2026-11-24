import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.user_query import UserQuery
from app.db.sql.models.enums import FamilyRole, Visibility
from app.db.sql.models.users import User
from app.services.family_service import FamilyService
from app.services.visibility_service import VisibilityService


async def _make_user(session: AsyncSession, email: str) -> User:
    return await UserQuery(session).create(
        id=uuid.uuid4(),
        email=email,
        hashed_password="not-a-real-hash",  # noqa: S106
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )


async def test_owner_can_always_view_their_own_record(dbsession: AsyncSession) -> None:
    """A record's own owner can see it regardless of visibility."""
    owner = await _make_user(dbsession, "owner@example.com")
    service = VisibilityService(owner.id, dbsession)

    assert await service.can_view(owner.id, Visibility.PRIVATE) is True
    assert await service.can_view(owner.id, Visibility.FAMILY) is True


async def test_stranger_cannot_view_a_private_record(dbsession: AsyncSession) -> None:
    """Someone outside the family can never see a private record."""
    owner = await _make_user(dbsession, "owner2@example.com")
    stranger = await _make_user(dbsession, "stranger2@example.com")
    service = VisibilityService(stranger.id, dbsession)

    assert await service.can_view(owner.id, Visibility.PRIVATE) is False


async def test_stranger_cannot_view_a_family_record_without_shared_family(
    dbsession: AsyncSession,
) -> None:
    """Family visibility only helps readers who actually share a family."""
    owner = await _make_user(dbsession, "owner3@example.com")
    stranger = await _make_user(dbsession, "stranger3@example.com")
    service = VisibilityService(stranger.id, dbsession)

    assert await service.can_view(owner.id, Visibility.FAMILY) is False


async def test_family_member_can_view_a_family_record(dbsession: AsyncSession) -> None:
    """A family member can see another member's FAMILY-visibility record."""
    owner = await _make_user(dbsession, "owner4@example.com")
    member = await _make_user(dbsession, "member4@example.com")
    family_service = FamilyService(dbsession)
    family = await family_service.create(owner, "The Smiths")
    await family_service.members.create(
        user_id=member.id, family_id=family.id, role=FamilyRole.MEMBER
    )

    service = VisibilityService(member.id, dbsession)

    assert await service.can_view(owner.id, Visibility.FAMILY) is True
    assert await service.can_view(owner.id, Visibility.PRIVATE) is False


async def test_visible_owner_ids_me_scope_is_just_the_requester(
    dbsession: AsyncSession,
) -> None:
    """Scope "me" never includes anyone but the requester."""
    owner = await _make_user(dbsession, "owner5@example.com")
    service = VisibilityService(owner.id, dbsession)

    assert await service.visible_owner_ids(scope="me") == {owner.id}


async def test_visible_owner_ids_family_scope_includes_every_member(
    dbsession: AsyncSession,
) -> None:
    """Scope "family" includes every member of the requester's family."""
    owner = await _make_user(dbsession, "owner6@example.com")
    member = await _make_user(dbsession, "member6@example.com")
    family_service = FamilyService(dbsession)
    family = await family_service.create(owner, "The Smiths")
    await family_service.members.create(
        user_id=member.id, family_id=family.id, role=FamilyRole.MEMBER
    )

    service = VisibilityService(owner.id, dbsession)

    assert await service.visible_owner_ids(scope="family") == {owner.id, member.id}


async def test_visible_owner_ids_family_scope_falls_back_when_unaffiliated(
    dbsession: AsyncSession,
) -> None:
    """A user with no family still gets a usable (self-only) owner set."""
    owner = await _make_user(dbsession, "owner7@example.com")
    service = VisibilityService(owner.id, dbsession)

    assert await service.visible_owner_ids(scope="family") == {owner.id}
