"""
Shared shapes every statement/bill parser produces.

``ImportService`` (the only caller) is written entirely against these
base class/models -- it never imports a concrete parser module
directly except through ``registry.py``'s lookup, so adding a new source
never touches the service.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class ParsedTransaction(BaseModel):
    """One row parsed out of a bank/broker statement export."""

    #: The provider's own transaction id, when the export has one.
    #: ``None`` means the parser must fall back to a hash-based dedupe
    #: key (see ``ImportedTransactionQuery``'s dedupe logic).
    dedupe_key: str | None
    occurred_at: date
    #: Signed: negative is a spend, positive is income.
    amount: Decimal
    description: str
    counterparty: str | None
    currency: str


class UnparseableRow(BaseModel):
    """
    One row a parser found but couldn't make sense of.

    Distinct from :class:`~app.libs.parsers.base.
    UnrecognizedFormatError`, which means the *whole file* doesn't match
    this source's format at all: this is "the file is a real export from
    this provider, and every other row parsed fine, but this one specific
    row didn't" (the mockup's "Row on page 3 couldn't be read" card,
    surfaced with its raw text and an "Add manually" shortcut). A parser
    should prefer returning a few of these over raising and losing every
    other row in the file to one bad line.
    """

    raw_text: str
    reason: str


class ParsedBillItem(BaseModel):
    """One product/line item parsed out of a receipt."""

    name: str
    amount: Decimal
    #: Freeform display text (e.g. "x2", "1.2 kg"), never a number --
    #: see SpentItem.quantity's own docstring for why.
    quantity: str | None


class ParsedBill(BaseModel):
    """One parsed receipt: a single purchase's line items."""

    merchant: str | None
    purchased_at: date | None
    total_amount: Decimal | None
    items: list[ParsedBillItem]


class UnrecognizedFormatError(Exception):
    """Raised when a file doesn't match its parser's expected shape at all."""


class UnsupportedContentTypeError(Exception):
    """Raised when a bill upload's content type isn't handled (e.g. a photo)."""


class BaseParser:
    """
    Base class every statement/bill parser inherits from.

    Subclasses override :meth:`parse` with their own input and result
    shapes (a statement parser returns rows, a bill parser one bill).
    """

    def parse(self, file_bytes: bytes, *args: Any, **kwargs: Any) -> Any:
        """
        Parse an uploaded file.

        :param file_bytes: the raw uploaded file.
        :param args: parser-specific positional arguments.
        :param kwargs: parser-specific keyword arguments.
        :raises NotImplementedError: always, subclasses must override.
        :return: parser-specific result.
        """
        raise NotImplementedError
