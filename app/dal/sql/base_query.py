from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


class BaseQuery[ModelT]:
    """
    Generic create/get/retrieve/update/delete operations for a SQL table.

    Set ``_model`` on a subclass to the mapped model it queries. Query
    classes with domain-specific needs (lookups other than by primary key,
    multi-table joins, ...) add their own methods on top of this.
    """

    _model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> ModelT:
        """
        Create a new row.

        :param kwargs: field values for the new row.
        :return: the created instance.
        """
        instance = self._model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get(self, pk: Any) -> ModelT | None:
        """
        Fetch a single row by primary key.

        :param pk: primary key value.
        :return: the instance, or ``None`` if it doesn't exist.
        """
        return await self.session.get(self._model, pk)

    async def retrieve(
        self,
        limit: int | None = None,
        offset: int | None = None,
        **filters: Any,
    ) -> list[ModelT]:
        """
        Fetch rows matching ``filters`` (exact match, ANDed together).

        :param limit: maximum number of rows to return.
        :param offset: number of matching rows to skip.
        :param filters: column-name/value pairs to filter on.
        :return: matching instances.
        """
        query = select(self._model)
        for field, value in filters.items():
            query = query.where(getattr(self._model, field) == value)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.exec(query)
        return list(result.all())

    async def update(self, pk: Any, **kwargs: Any) -> ModelT | None:
        """
        Update a row by primary key.

        :param pk: primary key value.
        :param kwargs: field values to set.
        :return: the updated instance, or ``None`` if it doesn't exist.
        """
        instance = await self.get(pk)
        if instance is None:
            return None
        for field, value in kwargs.items():
            setattr(instance, field, value)
        await self.session.flush()
        return instance

    async def delete(self, pk: Any) -> None:
        """
        Delete a row by primary key.

        Does nothing if it doesn't exist.

        :param pk: primary key value.
        """
        instance = await self.get(pk)
        if instance is not None:
            await self.session.delete(instance)
            await self.session.flush()
