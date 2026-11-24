"""
bunq statement CSV parser.

**Unverified against a real export -- lower confidence than the Wise
parser.** bunq's app primarily promotes CAMT.053 (ISO 20022 XML) and
MT940 exports; its CSV export's exact column names are not something
this module can cite from a verified-current source. The columns
guessed below (``Date``, ``Amount``, ``Counterparty``, ``Description``)
are a reasonable placeholder shape, not a confirmed one. **Get one real
bunq export (CSV, or add a CAMT.053/MT940 parser instead if that's what
bunq's UI actually offers) before relying on this in production**, per
the build plan's Phase 9 caveat -- this parser is scaffolding for that
verification pass, not a finished implementation.

Fails loudly (``UnrecognizedFormatError``) rather than guessing on an
unrecognized shape, same as the Wise parser.
"""

import csv
import io
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.libs.parsers.base import (
    BaseParser,
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)

_DATE_COLUMNS = ("Date",)
_AMOUNT_COLUMNS = ("Amount",)
_CURRENCY_COLUMNS = ("Currency",)
_DESCRIPTION_COLUMNS = ("Description",)
_COUNTERPARTY_COLUMNS = ("Counterparty", "Name")

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")


def _find_column(header: Sequence[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in header:
            return candidate
    return None


def _parse_date(value: str) -> date:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise UnrecognizedFormatError(f"Unrecognized date format: {value!r}")


class BunqStatementParser(BaseParser):
    """Parses a bunq CSV statement export into transactions."""

    def parse(self, file_bytes: bytes) -> list[ParsedTransaction | UnparseableRow]:
        """
        Parse a bunq CSV export.

        :param file_bytes: the raw uploaded file.
        :raises UnrecognizedFormatError: if it doesn't look like a bunq
            CSV export (missing the date/amount/description columns
            this parser requires).
        :return: every transaction row found.
        """
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnrecognizedFormatError("Not a UTF-8 text file.") from exc

        # bunq's CSV export is semicolon-delimited; fall back to comma if
        # the sniffed header doesn't contain a semicolon at all.
        delimiter = ";" if ";" in text.splitlines()[0] else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        header = reader.fieldnames
        if header is None:
            raise UnrecognizedFormatError("Empty file.")

        date_col = _find_column(header, _DATE_COLUMNS)
        amount_col = _find_column(header, _AMOUNT_COLUMNS)
        description_col = _find_column(header, _DESCRIPTION_COLUMNS)
        if date_col is None or amount_col is None or description_col is None:
            raise UnrecognizedFormatError(
                "Missing expected bunq columns (Date/Amount/Description)."
            )
        currency_col = _find_column(header, _CURRENCY_COLUMNS)
        counterparty_col = _find_column(header, _COUNTERPARTY_COLUMNS)

        transactions: list[ParsedTransaction | UnparseableRow] = []
        for row in reader:
            try:
                amount = Decimal(row[amount_col].strip().replace(",", "."))
            except (InvalidOperation, AttributeError, KeyError) as exc:
                raise UnrecognizedFormatError(
                    f"Unparseable amount: {row.get(amount_col)!r}"
                ) from exc
            transactions.append(
                ParsedTransaction(
                    # bunq's CSV export has no confirmed stable per-row
                    # id column -- fall back to the hash-based dedupe key
                    # (see ImportedTransactionQuery) until one is found.
                    dedupe_key=None,
                    occurred_at=_parse_date(row[date_col]),
                    amount=amount,
                    description=row.get(description_col, "").strip(),
                    counterparty=(
                        row.get(counterparty_col, "").strip()
                        if counterparty_col
                        else None
                    )
                    or None,
                    currency=(row.get(currency_col, "").strip() if currency_col else "")
                    or "EUR",
                )
            )
        return transactions
