import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.role_based import (
    Permission,
    RolePermission,
    UserPermission,
    UserRole,
)


class PermissionDAO(BaseQuery[Permission]):
    """RBAC queries for the role/permission tables, via SQLModel."""

    _model = Permission

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_effective_permissions(self, user_id: uuid.UUID) -> set[str]:
        """
        Return every permission name the user holds, directly or via a role.

        :param user_id: user to look up.
        :return: set of permission names.
        """
        role_ids = (
            await self.session.exec(
                select(UserRole.role_id).where(UserRole.user_id == user_id)
            )
        ).all()

        permission_ids: set[int] = set()
        if role_ids:
            role_permission_ids = (
                await self.session.exec(
                    select(RolePermission.permission_id).where(
                        col(RolePermission.role_id).in_(role_ids)
                    )
                )
            ).all()
            permission_ids.update(role_permission_ids)

        user_permission_ids = (
            await self.session.exec(
                select(UserPermission.permission_id).where(
                    UserPermission.user_id == user_id
                )
            )
        ).all()
        permission_ids.update(user_permission_ids)

        if not permission_ids:
            return set()

        names = (
            await self.session.exec(
                select(Permission.name).where(
                    col(Permission.id).in_(list(permission_ids))
                )
            )
        ).all()
        return set(names)
