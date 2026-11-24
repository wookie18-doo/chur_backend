from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.categories import get_category_service
from app.api.v1.categories.schema import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)
from app.db.sql.models.category import Category
from app.db.sql.models.enums import CategoryKind
from app.db.sql.models.users import User
from app.services.category_service import (
    CategoryInUseError,
    CategoryNotOwnedError,
    CategoryService,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    kind: CategoryKind,
    user: RequestUser = Depends(require_auth),
    category_service: CategoryService = Depends(get_category_service),
) -> list[Category]:
    """
    List every category of ``kind`` the current user may use.

    :param kind: expense or income.
    :param user: the authenticated user.
    :param category_service: category service.
    :return: built-in categories plus the user's own.
    """
    return await category_service.list_visible(cast(User, user.unwrap()), kind)


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    user: RequestUser = Depends(require_auth),
    category_service: CategoryService = Depends(get_category_service),
) -> Category:
    """
    Create a custom category owned by the current user.

    :param payload: category-creation payload.
    :param user: the authenticated user.
    :param category_service: category service.
    :return: the created category.
    """
    return await category_service.create(
        cast(User, user.unwrap()), payload.name, payload.kind, payload.color
    )


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    user: RequestUser = Depends(require_auth),
    category_service: CategoryService = Depends(get_category_service),
) -> Category:
    """
    Update a custom category owned by the current user.

    :param category_id: category to update.
    :param payload: fields to change; omitted ones stay as they are.
    :param user: the authenticated user.
    :param category_service: category service.
    :raises HTTPException: 404, if it's built-in or owned by someone else.
    :return: the updated category.
    """
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("name") is None:
        fields.pop("name", None)
    try:
        return await category_service.update(
            cast(User, user.unwrap()), category_id, **fields
        )
    except CategoryNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found."
        ) from exc


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    user: RequestUser = Depends(require_auth),
    category_service: CategoryService = Depends(get_category_service),
) -> None:
    """
    Delete a custom category owned by the current user.

    :param category_id: category to delete.
    :param user: the authenticated user.
    :param category_service: category service.
    :raises HTTPException: 404, if it's built-in or owned by someone
        else; 409, if a spent/income/spent-item still uses it.
    """
    try:
        await category_service.delete(cast(User, user.unwrap()), category_id)
    except CategoryNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found."
        ) from exc
    except CategoryInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category that's already used by an entry can't be deleted.",
        ) from exc
