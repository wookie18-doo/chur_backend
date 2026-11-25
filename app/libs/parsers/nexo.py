"""
Nexo transactions CSV parser.

Built against Nexo's "Transactions" CSV export (columns ``Transaction,
Type, Credit Line, Input Currency, Input Amount, Output Currency, Output
Amount, USD Equivalent, Fee, Fee Currency, Details, Date / Time (UTC)``).

The export mixes the Nexo Card's fiat flow with the crypto wallet's
internal bookkeeping: every card purchase also emits an ``Exchange``
(crypto -> EURX), a ``Credit Card Fiatx Exchange To Withdraw`` (EURX ->
EUR) and, on settlement, a ``Withdraw Exchanged`` row for the same money.
Only the card's own rows are imported -- purchases, refunds and card fees,
in the card's (output) currency -- so a purchase is counted once; the
wallet-side rows (exchanges, interest, crypto top-ups/withdrawals) are
skipped, as are ``rejected`` rows. ``dedupe_key`` is Nexo's own
transaction id.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.libs.parsers.base import (
    BaseParser,
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)

_REQUIRED_COLUMNS = frozenset(
    {
        "Transaction",
        "Type",
        "Output Currency",
        "Output Amount",
        "Details",
        "Date / Time (UTC)",
    }
)
_PURCHASE = "Nexo Card Purchase"
_REFUND = "Nexo Card Refund"
_FEE = "Nexo Card Transaction Fee"
#: Card row type -> the sign its (always positive) output amount gets.
_CARD_TYPES = {_PURCHASE: -1, _REFUND: 1, _FEE: -1}
_REJECTED = "rejected"
_CENT = Decimal("0.01")


class NexoStatementParser(BaseParser):
    """Parses a Nexo transactions CSV export into card transactions."""

    def parse(self, file_bytes: bytes) -> list[ParsedTransaction | UnparseableRow]:
        """
        Parse a Nexo transactions CSV export.

        :param file_bytes: the raw uploaded file.
        :raises UnrecognizedFormatError: if it isn't a UTF-8 CSV with Nexo's
            columns. A single card row with a bad date or amount is an
            :class:`UnparseableRow` in the result instead.
        :return: every card purchase, refund and fee, in file order.
        """
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnrecognizedFormatError("Not a UTF-8 text file.") from exc

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None or not set(reader.fieldnames) >= _REQUIRED_COLUMNS:
            raise UnrecognizedFormatError("Missing expected Nexo CSV columns.")

        rows: list[ParsedTransaction | UnparseableRow] = []
        for row in reader:
            sign = _CARD_TYPES.get((row["Type"] or "").strip())
            if sign is None:
                continue
            status, _, details = (row["Details"] or "").partition(" / ")
            if status.strip().lower() == _REJECTED:
                continue
            rows.append(_build(row, sign, details.strip()))
        return rows


def _build(
    row: dict[str, str], sign: int, details: str
) -> ParsedTransaction | UnparseableRow:
    try:
        amount = sign * abs(Decimal(row["Output Amount"].strip())).quantize(_CENT)
        occurred_at = datetime.strptime(
            row["Date / Time (UTC)"].strip(), "%Y-%m-%d %H:%M:%S"
        ).date()
    except (InvalidOperation, ValueError, AttributeError) as exc:
        return UnparseableRow(
            raw_text=",".join(str(value) for value in row.values()),
            reason=str(exc),
        )
    kind = row["Type"].strip()
    counterparty = None
    description = details
    if kind in (_PURCHASE, _REFUND):
        counterparty = details.split(" | ", maxsplit=1)[0].strip() or None
    if kind == _REFUND:
        description = f"Refund: {details}"
    return ParsedTransaction(
        dedupe_key=row["Transaction"].strip() or None,
        occurred_at=occurred_at,
        amount=amount,
        description=description or kind,
        counterparty=counterparty,
        currency=(row["Output Currency"] or "").strip().upper() or "EUR",
    )
