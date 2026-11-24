"""
Router in front of the concrete statement-parse-job DAO.

Inherits every generic ``create``/``get``/``retrieve``/``update``/``delete``
operation from the backend's ``StatementParseJobDAO``; ``StatementParseService``
is written against this class only.
"""

from app.dal.sql.statement_parse_job_dao import StatementParseJobDAO


class StatementParseJobQuery(StatementParseJobDAO):
    """Everything ``StatementParseService`` needs to track parse jobs."""
