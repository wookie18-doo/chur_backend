"""
Wise (formerly TransferWise) statement CSV parser.

**Unverified against a real export.** Wise's own documentation and
publicly known exports describe a CSV with (at least) columns
``TransferWise ID``/``ID``, ``Date``, ``Amount``, ``Currency``,
``Description``/``Merchant``, and ``Payee Name``/``Payer Name`` -- this
module is written against that recollection, not a sample file pinned in
``tests/fixtures/imports/``. Wise's exact column set has changed over
time and can vary by account/currency. **Before relying on this in
production, get one real Wise CSV export and update this parser (and add
it as a test fixture) to match it exactly** -- this is the single
biggest risk flagged in the build plan's Phase 9.

Rather than guess silently, this parser fails loudly
(``UnrecognizedFormatError``) if the minimum columns it needs aren't
present, instead of half-parsing a format it doesn't actually recognize.
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

#: Column names this parser accepts for each logical field, in
#: preference order -- Wise has used more than one header spelling.
_DATE_COLUMNS = ("Date",)
_AMOUNT_COLUMNS = ("Amount",)
_CURRENCY_COLUMNS = ("Currency",)
_DESCRIPTION_COLUMNS = ("Description", "Merchant")
_COUNTERPARTY_COLUMNS = ("Payee Name", "Payer Name", "Merchant")
_ID_COLUMNS = ("TransferWise ID", "Wise ID", "ID")

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
    raise ValueError(f"Unrecognized date format: {value!r}")


class WiseStatementParser(BaseParser):
    """Parses a Wise CSV statement export into transactions."""

    def parse(self, file_bytes: bytes) -> list[ParsedTransaction | UnparseableRow]:
        """
        Parse a Wise CSV export.

        :param file_bytes: the raw uploaded file.
        :raises UnrecognizedFormatError: if it doesn't look like a Wise
            CSV export at all (missing the date/amount/description
            columns this parser requires). A single row with a bad date
            or amount is an :class:`UnparseableRow` in the result
            instead -- the rest of the file still gets imported.
        :return: every row found, transactions mixed with unparseable ones.
        """
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnrecognizedFormatError("Not a UTF-8 text file.") from exc

        reader = csv.DictReader(io.StringIO(text))
        header = reader.fieldnames
        if header is None:
            raise UnrecognizedFormatError("Empty file.")

        date_col = _find_column(header, _DATE_COLUMNS)
        amount_col = _find_column(header, _AMOUNT_COLUMNS)
        description_col = _find_column(header, _DESCRIPTION_COLUMNS)
        if date_col is None or amount_col is None or description_col is None:
            raise UnrecognizedFormatError(
                "Missing expected Wise columns (Date/Amount/Description)."
            )
        currency_col = _find_column(header, _CURRENCY_COLUMNS)
        counterparty_col = _find_column(header, _COUNTERPARTY_COLUMNS)
        id_col = _find_column(header, _ID_COLUMNS)

        rows: list[ParsedTransaction | UnparseableRow] = []
        for row in reader:
            try:
                amount = Decimal(row[amount_col].strip())
                occurred_at = _parse_date(row[date_col])
            except (InvalidOperation, ValueError, AttributeError, KeyError) as exc:
                rows.append(UnparseableRow(raw_text=str(row), reason=str(exc)))
                continue
            rows.append(
                ParsedTransaction(
                    dedupe_key=row.get(id_col) if id_col else None,
                    occurred_at=occurred_at,
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
        return rows
