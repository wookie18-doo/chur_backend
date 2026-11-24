from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.family import Family


class FamilyDAO(BaseQuery[Family]):
    """SQL queries for the family table, via SQLModel."""

    _model = Family
