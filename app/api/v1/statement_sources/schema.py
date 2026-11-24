from pydantic import BaseModel, ConfigDict, Field


class StatementSourceRead(BaseModel):
    """Represents a statement source returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str


class StatementSourceCreate(BaseModel):
    """Represents a statement-source creation payload."""

    name: str = Field(min_length=1, max_length=100)
