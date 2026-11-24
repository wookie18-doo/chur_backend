from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.statement_source_query import StatementSourceQuery
from app.db.sql.models.statement_source import StatementSourceRecord

MARKET_BILL_CODE = "market_bill"


class StatementSourceNotFoundError(Exception):
    """Raised when no statement source matches the given id."""


class StatementSourceConflictError(Exception):
    """Raised when a statement source with the same name already exists."""


class StatementSourceInvalidNameError(Exception):
    """Raised when a statement source name has non-latin symbols."""


class StatementSourceService:
    """Business logic for the catalogue of statement sources."""

    def __init__(self, session: AsyncSession) -> None:
        self.sources = StatementSourceQuery(session)

    async def list_sources(self) -> list[StatementSourceRecord]:
        """
        List every statement source.

        :return: all sources, ordered by name.
        """
        return await self.sources.list_all()

    async def retrieve(self, source_id: int) -> StatementSourceRecord:
        """
        Fetch one statement source by id.

        :param source_id: source id.
        :raises StatementSourceNotFoundError: if it doesn't exist.
        :return: the source.
        """
        source = await self.sources.get(source_id)
        if source is None:
            raise StatementSourceNotFoundError
        return source

    async def get_by_code(self, code: str) -> StatementSourceRecord | None:
        """
        Fetch a statement source by its code.

        :param code: the source's ``code`` (see ``StatementSourceRecord``).
        :return: the source, or ``None`` if none has that code.
        """
        for source in await self.sources.list_all():
            if source.code == code:
                return source
        return None

    async def create(self, name: str) -> StatementSourceRecord:
        """
        Create a statement source.

        :param name: unique source name.
        :raises StatementSourceInvalidNameError: if the name isn't latin.
        :raises StatementSourceConflictError: if the name is taken.
        :return: the created source.
        """
        if await self.sources.get_by_name(name) is not None:
            raise StatementSourceConflictError
        try:
            return await self.sources.create(name=name)
        except ValueError as exc:
            raise StatementSourceInvalidNameError from exc
        except IntegrityError as exc:
            # A failed flush leaves the transaction aborted until rolled back.
            await self.sources.session.rollback()
            raise StatementSourceConflictError from exc
