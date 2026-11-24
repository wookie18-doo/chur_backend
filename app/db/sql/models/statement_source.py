import re

from sqlalchemy.orm import validates
from sqlmodel import Field

from app.db.sql.base import Base


class StatementSourceRecord(Base, table=True):
    """
    A provider statements can be imported from (Wise, bunq, ...).

    ``code`` (the sanitized name) is what picks the parser. The built-in
    ``market_bill`` source is only valid for an ``ImportJob``, never for an
    ``Account`` -- enforced in the service layer.
    """

    __tablename__ = "statement_source"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, unique=True, index=True)

    @property
    def code(self) -> str:
        """
        Machine-friendly form of the name.

        Lower-cased, with every run of non-alphanumeric characters
        collapsed to a single underscore and edge underscores trimmed.
        """
        return re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_")

    @validates("name")
    def _validate_name(self, _key: str, value: str) -> str:
        if not value.isascii() or not re.search(r"[A-Za-z]", value):
            raise ValueError("Name must use latin symbols only.")
        return value
