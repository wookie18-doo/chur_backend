from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.category_query import CategoryQuery
from app.db.sql.models.category import Category
from app.db.sql.models.enums import CategoryColor, CategoryKind
from app.db.sql.models.users import User


class CategoryNotOwnedError(Exception):
    """Raised when a user tries to modify a category they don't own."""


class CategoryInUseError(Exception):
    """Raised when a category can't be deleted because something uses it."""


class CategoryService:
    """
    Business logic for filing spents/incomes under categories.

    Builds its own :class:`~app.dal.category_query.CategoryQuery` from
    the db session it's given -- callers never construct a query object
    themselves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.categories = CategoryQuery(session)

    async def list_visible(self, user: User, kind: CategoryKind) -> list[Category]:
        """
        List every category of ``kind`` a user may use.

        :param user: user requesting the list.
        :param kind: expense or income.
        :return: built-in categories plus the user's own.
        """
        return await self.categories.list_visible(user.id, kind)

    async def create(
        self,
        user: User,
        name: str,
        kind: CategoryKind,
        color: CategoryColor | None = None,
    ) -> Category:
        """
        Create a custom category owned by ``user``.

        :param user: the category's owner.
        :param name: category name.
        :param kind: expense or income.
        :param color: swatch to display it with, if any.
        :return: the created category.
        """
        return await self.categories.create(
            name=name, kind=kind, owner_id=user.id, color=color
        )

    async def update(self, user: User, category_id: int, **fields: Any) -> Category:
        """
        Update a custom category owned by ``user``.

        :param user: user requesting the update.
        :param category_id: category to update.
        :param fields: ``name``/``color`` values to set.
        :raises CategoryNotOwnedError: if the category is built-in or
            owned by someone else.
        :return: the updated category.
        """
        category = await self.categories.get(category_id)
        if category is None or category.owner_id != user.id:
            raise CategoryNotOwnedError
        updated = await self.categories.update(category_id, **fields)
        assert updated is not None  # noqa: S101
        return updated

    async def delete(self, user: User, category_id: int) -> None:
        """
        Delete a custom category owned by ``user``.

        :param user: user requesting the deletion.
        :param category_id: category to delete.
        :raises CategoryNotOwnedError: if the category is built-in or
            owned by someone else.
        :raises CategoryInUseError: if a spent/income/spent-item still
            references it.
        """
        category = await self.categories.get(category_id)
        if category is None or category.owner_id != user.id:
            raise CategoryNotOwnedError
        try:
            await self.categories.delete(category_id)
        except IntegrityError as exc:
            # See AccountService.delete's matching comment: a failed flush
            # leaves the session's transaction aborted until rolled back.
            await self.categories.session.rollback()
            raise CategoryInUseError from exc
