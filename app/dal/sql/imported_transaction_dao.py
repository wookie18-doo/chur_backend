from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.import_job import ImportedTransaction


class ImportedTransactionDAO(BaseQuery[ImportedTransaction]):
    """SQL queries for the imported_transaction table, via SQLModel."""

    _model = ImportedTransaction
