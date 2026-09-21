from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.permission_query import PermissionQuery
from app.db.sql.models.users import User


class PermissionService:
    """
    Business logic for checking what a user is allowed to do.

    Transport layers (``app.api.dependencies.permissions``,
    ``app.gql.permissions``) call this service and translate its decisions
    into whatever error shape fits their protocol -- an HTTP status code, a
    GraphQL error, and so on. Add your own role/permission rules here, not
    in the routers or resolvers.
    Builds its own :class:`~app.dal.permission_query.PermissionQuery` from
    the db session/connection it's given -- callers never construct a query
    object themselves.
    """

    def __init__(self, user: User, session: AsyncSession | None = None) -> None:
        self.user = user
        self.queries = PermissionQuery(session) if session is not None else None

    def is_active(self) -> bool:
        """
        Check that the user account is active.

        :return: whether the user is active.
        """
        return self.user.is_active

    def is_superuser(self) -> bool:
        """
        Check that the user has superuser privileges.

        :return: whether the user is a superuser.
        """
        return self.user.is_superuser

    async def has_permissions(self, permissions: list[str]) -> bool:
        """
        Check that the user holds every permission in ``permissions``.

        A permission can reach the user directly or through one of their
        roles -- that's resolved by whatever
        :class:`~app.dal.permission_query.PermissionQuery`
        implementation this service was built with. Superusers always pass.

        :param permissions: permission names to require.
        :return: whether the user holds all of them.
        :raises RuntimeError: if the service wasn't built with a queries object.
        """
        if not permissions or self.user.is_superuser:
            return True
        if self.queries is None:
            raise RuntimeError(
                "PermissionService.has_permissions() requires a queries object."
            )
        granted = await self.queries.get_effective_permissions(self.user.id)
        return set(permissions).issubset(granted)
