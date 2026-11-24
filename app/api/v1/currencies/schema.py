from pydantic import BaseModel, ConfigDict


class CurrencyRead(BaseModel):
    """Represents a currency returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    is_active: bool
