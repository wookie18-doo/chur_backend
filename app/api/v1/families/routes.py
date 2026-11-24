import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.families import get_family_service
from app.api.v1.families.schema import (
    FamilyCreate,
    FamilyMemberAdd,
    FamilyMemberRead,
    FamilyMemberRoleUpdate,
    FamilyRead,
    FamilyUpdate,
    FamilyWithMembers,
)
from app.db.sql.models.family import Family
from app.db.sql.models.users import User
from app.services.family_service import (
    AlreadyInFamilyError,
    FamilyService,
    NotFamilyOwnerError,
    NotInFamilyError,
    OwnerCannotLeaveError,
    UserNotFoundError,
)

router = APIRouter(prefix="/families", tags=["families"])


@router.post("", response_model=FamilyRead, status_code=status.HTTP_201_CREATED)
async def create_family(
    payload: FamilyCreate,
    user: RequestUser = Depends(require_auth),
    family_service: FamilyService = Depends(get_family_service),
) -> Family:
    """
    Create a new family owned by the current user.

    :param payload: family-creation payload.
    :param user: the authenticated user.
    :param family_service: family service.
    :raises HTTPException: 409, if the user already belongs to a family.
    :return: the created family.
    """
    try:
        return await family_service.create(cast(User, user.unwrap()), payload.name)
    except AlreadyInFamilyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already a member of a family.",
        ) from exc


@router.get("/me", response_model=FamilyWithMembers)
async def read_own_family(
    user: RequestUser = Depends(require_auth),
    family_service: FamilyService = Depends(get_family_service),
) -> FamilyWithMembers:
    """
    Return the current user's family together with its members.

    :param user: the authenticated user.
    :param family_service: family service.
    :raises HTTPException: 404, if the user doesn't belong to a family.
    :return: the family and its members.
    """
    actor = cast(User, user.unwrap())
    family = await family_service.get_own_family(actor)
    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of a family."
        )
    members = await family_service.list_members_with_users(actor)
    return FamilyWithMembers(
        id=family.id,
        name=family.name,
        members=[FamilyMemberRead.build(member, u) for member, u in members],
    )


@router.patch("/me", response_model=FamilyRead)
async def rename_family(
    payload: FamilyUpdate,
    user: RequestUser = Depends(require_auth),
    family_service: FamilyService = Depends(get_family_service),
) -> Family:
    """
    Rename the current user's family.

    :param payload: the new name.
    :param user: the authenticated user -- must own their family.
    :param family_service: family service.
    :raises HTTPException: 404/403, see the service's own errors.
    :return: the renamed family.
    """
    try:
        return await family_service.rename(cast(User, user.unwrap()), payload.name)
    except NotInFamilyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of a family."
        ) from exc
    except NotFamilyOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can rename the family.",
        ) from exc


@router.post(
    "/members", response_model=FamilyMemberRead, status_code=status.HTTP_201_CREATED
)
async def add_member(
    payload: FamilyMemberAdd,
    user: RequestUser = Depends(require_auth),
    family_service: FamilyService = Depends(get_family_service),
) -> FamilyMemberRead:
    """
    Add a user to the current user's family, by id or email.

    :param payload: id or email of the user to add.
    :param user: the authenticated user -- must own their family.
    :param family_service: family service.
    :raises HTTPException: 404/403/409, see the service's own errors.
    :return: the created membership.
    """
    try:
        member, added = await family_service.add_member(
            cast(User, user.unwrap()), payload.user_id, email=payload.email
        )
        return FamilyMemberRead.build(member, added)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ) from exc
    except NotInFamilyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of a family."
        ) from exc
    except NotFamilyOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can add members.",
        ) from exc
    except AlreadyInFamilyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That user already belongs to a family.",
        ) from exc


@router.patch("/members/{user_id}", response_model=FamilyMemberRead)
async def set_member_role(
    user_id: uuid.UUID,
    payload: FamilyMemberRoleUpdate,
    user: RequestUser = Depends(require_auth),
    family_service: FamilyService = Depends(get_family_service),
) -> FamilyMemberRead:
    """
    Change a member's role; promoting to owner transfers ownership.

    :param user_id: member whose role changes.
    :param payload: the new role.
    :param user: the authenticated user -- must own their family.
    :param family_service: family service.
    :raises HTTPException: 404/403/409, see the service's own errors.
    :return: the updated membership.
    """
    try:
        member, target = await family_service.set_member_role(
            cast(User, user.unwrap()), user_id, payload.role
        )
        return FamilyMemberRead.build(member, target)
    except NotInFamilyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found."
        ) from exc
    except NotFamilyOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can change roles.",
        ) from exc
    except OwnerCannotLeaveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Owners can't demote themselves; make someone else the owner.",
        ) from exc


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    family_service: FamilyService = Depends(get_family_service),
) -> None:
    """
    Remove a member from the current user's family, or leave it.

    Removing yourself is always allowed (leaving); removing anyone else
    requires being the family's owner.

    :param user_id: user to remove.
    :param user: the authenticated user.
    :param family_service: family service.
    :raises HTTPException: 404/403/409, see the service's own errors.
    """
    actor = cast(User, user.unwrap())
    try:
        if user_id == actor.id:
            await family_service.leave(actor)
        else:
            await family_service.remove_member(actor, user_id)
    except NotInFamilyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of a family."
        ) from exc
    except NotFamilyOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can remove other members.",
        ) from exc
    except OwnerCannotLeaveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The family owner can't leave or be removed; delete the family "
            "instead.",
        ) from exc
