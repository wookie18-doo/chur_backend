"""Router in front of the concrete statement-source DAO."""

from sqlmodel import col, select

from app.dal.sql.statement_source_dao import StatementSourceDAO
from app.db.sql.models.statement_source import StatementSourceRecord


class StatementSourceQuery(StatementSourceDAO):
    """Everything ``StatementSourceService`` needs to read and write sources."""

    async def list_all(self) -> list[StatementSourceRecord]:
        """
        Fetch every statement source.

        :return: all sources, ordered by name.
        """
        query = select(StatementSourceRecord).order_by(col(StatementSourceRecord.name))
        result = await self.session.exec(query)
        return list(result.all())

    async def get_by_name(self, name: str) -> StatementSourceRecord | None:
        """
        Fetch a source by its unique name.

        :param name: source name.
        :return: the source, or ``None`` if there is none with that name.
        """
        query = select(StatementSourceRecord).where(StatementSourceRecord.name == name)
        return (await self.session.exec(query)).first()
