from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Base(SQLModel):
    """
    Base for all models.

    ``created_at``/``updated_at`` use ``sa_column_kwargs`` rather than
    ``sa_column`` -- ``sa_column`` would hand every subclass the exact same
    ``Column`` instance, and SQLAlchemy refuses to attach one Column object
    to more than one Table. ``sa_column_kwargs`` lets each subclass's table
    get its own freshly built column instead.
    """

    created_at: datetime = Field(sa_column_kwargs={"server_default": sa.func.now()})
    updated_at: datetime = Field(
        sa_column_kwargs={"server_default": sa.func.now(), "onupdate": sa.func.now()}
    )
