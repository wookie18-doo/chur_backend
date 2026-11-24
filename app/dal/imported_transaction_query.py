"""
Router in front of the concrete imported-transaction DAO.

``ImportedTransactionQuery`` inherits directly from the concrete
``ImportedTransactionDAO`` for whichever backend was chosen, so every
generic ``create``/``get``/``retrieve``/``update``/``delete`` operation
is already available on it as an inherited method, and it only adds the
domain-specific lookups ``ImportService`` needs on top of them.
"""

import uuid

from sqlmodel import select

from app.dal.sql.imported_transaction_dao import ImportedTransactionDAO
from app.db.sql.models.import_job import ImportedTransaction


class ImportedTransactionQuery(ImportedTransactionDAO):
    """Everything ``ImportService`` needs for imported-transaction bookkeeping."""

    async def exists_by_dedupe_key(
        self, user_id: uuid.UUID, source_id: int, dedupe_key: str
    ) -> bool:
        """
        Check whether a transaction with this dedupe key was already imported.

        This is what makes re-uploading an overlapping statement safe
        instead of double-counting transactions.

        :param user_id: owner the dedupe key is scoped to.
        :param source_id: which provider's export this key came from.
        :param dedupe_key: the row's dedupe key (provider transaction id,
            or a hash of its date/amount/description).
        :return: whether a matching row already exists.
        """
        query = (
            select(ImportedTransaction.id)
            .where(ImportedTransaction.user_id == user_id)
            .where(ImportedTransaction.source_id == source_id)
            .where(ImportedTransaction.dedupe_key == dedupe_key)
            .limit(1)
        )
        result = await self.session.exec(query)
        return result.first() is not None

    async def list_by_job(self, import_job_id: uuid.UUID) -> list[ImportedTransaction]:
        """
        Fetch every parsed row belonging to an import job.

        :param import_job_id: parent job.
        :return: its rows.
        """
        return await self.retrieve(import_job_id=import_job_id)
