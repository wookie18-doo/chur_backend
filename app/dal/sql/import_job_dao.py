from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.import_job import ImportJob


class ImportJobDAO(BaseQuery[ImportJob]):
    """SQL queries for the import_job table, via SQLModel."""

    _model = ImportJob
