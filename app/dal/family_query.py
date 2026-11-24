"""
Router in front of the concrete family DAO.

``FamilyQuery`` inherits directly from the concrete ``FamilyDAO`` for
whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it.
``FamilyService`` is written entirely against this class and builds it
itself from a db session/connection -- callers never construct a query
object themselves.
"""

from app.dal.sql.family_dao import FamilyDAO


class FamilyQuery(FamilyDAO):
    """Everything ``FamilyService`` needs to read and write family data."""
