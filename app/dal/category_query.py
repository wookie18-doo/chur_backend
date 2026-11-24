"""
Router in front of the concrete category DAO.

``CategoryQuery`` inherits directly from the concrete ``CategoryDAO`` for
whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``CategoryService`` needs on top of them.
"""

import uuid

from sqlmodel import col, or_, select

from app.dal.sql.category_dao import CategoryDAO
from app.db.sql.models.category import Category
from app.db.sql.models.enums import CategoryKind


class CategoryQuery(CategoryDAO):
    """Everything ``CategoryService`` needs to read and write category data."""

    async def list_visible(
        self, user_id: uuid.UUID, kind: CategoryKind
    ) -> list[Category]:
        """
        Fetch every category of ``kind`` a user may file a record under.

        That's every built-in category (``owner_id IS NULL``) plus the
        user's own custom ones.

        :param user_id: user requesting the list.
        :param kind: expense or income.
        :return: matching categories, built-ins first.
        """
        query = (
            select(Category)
            .where(Category.kind == kind)
            .where(
                or_(
                    col(Category.owner_id).is_(None),
                    Category.owner_id == user_id,
                )
            )
            .order_by(col(Category.owner_id).is_not(None), Category.name)
        )
        result = await self.session.exec(query)
        return list(result.all())

    async def get_builtin(self, name: str, kind: CategoryKind) -> Category | None:
        """
        Fetch a specific built-in category by name.

        Used by ``ImportService`` for its auto-categorization fallbacks
        (e.g. "Uncategorized" for a statement row, "Groceries" for a
        bill) -- built-ins only, never a user's own custom category of
        the same name.

        :param name: exact built-in category name.
        :param kind: expense or income.
        :return: the category, or ``None`` if no built-in of that name exists.
        """
        query = (
            select(Category)
            .where(Category.kind == kind)
            .where(col(Category.owner_id).is_(None))
            .where(Category.name == name)
        )
        result = await self.session.exec(query)
        return result.first()
