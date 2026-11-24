from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.family import FamilyMember


class FamilyMemberDAO(BaseQuery[FamilyMember]):
    """SQL queries for the family_member table, via SQLModel."""

    _model = FamilyMember
