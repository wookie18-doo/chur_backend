"""
Router in front of the concrete import-job DAO.

``ImportJobQuery`` inherits directly from the concrete ``ImportJobDAO``
for whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``ImportService`` needs on top of them.
"""

import uuid

from app.dal.sql.import_job_dao import ImportJobDAO
from app.db.sql.models.import_job import ImportJob


class ImportJobQuery(ImportJobDAO):
    """Everything ``ImportService`` needs to read and write import jobs."""

    async def list_for_user(self, user_id: uuid.UUID) -> list[ImportJob]:
        """
        Fetch a user's import jobs.

        Imports are always "me"-scoped, never family-visible -- a
        statement upload is never something to share.

        :param user_id: owner to look up.
        :return: matching jobs.
        """
        return await self.retrieve(user_id=user_id)
