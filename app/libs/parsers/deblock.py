"""
Deblock account-statement PDF parser.

Built against Deblock's "EUR Account Statement" PDF export (text layer).
Each page repeats a ``Date | Value date | Transaction | Debit | Credit``
table where a row's amount sits in *either* the Debit or the Credit
column and carries no sign, so the column is told apart by the amount's
horizontal position under the page's own header. Dates carry no year; it
is taken from the "Account transactions from ... to ..." period line.
The export has no per-row id, so ``dedupe_key`` is a hash that includes
the row's occurrence number among otherwise identical rows.
"""

import hashlib
import io
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

import pdfplumber
from pdfplumber.page import Page

from app.libs.parsers.base import (
    BaseParser,
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)
from app.libs.parsers.pdf import group_lines

_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        start=1,
    )
}
_MONTH = "|".join(_MONTHS)
_CURRENCY = re.compile(r"^([A-Z]{3}) Account Statement\b", re.MULTILINE)
_PERIOD = re.compile(
    rf"Account transactions from \d{{1,2}} ({_MONTH}) (\d{{4}}) "
    rf"to (\d{{1,2}}) ({_MONTH}) (\d{{4}})",
    re.IGNORECASE,
)
_ROW_START = re.compile(rf"^\d{{1,2}} ({_MONTH})\b", re.IGNORECASE)
_ROW = re.compile(
    rf"^(?P<day>\d{{1,2}}) (?P<month>{_MONTH}) "
    rf"(?P<vday>\d{{1,2}}) (?P<vmonth>{_MONTH}) "
    r"(?P<kind>.+?) \"(?P<counterparty>.*)\" "
    r"(?P<amount>\d[\d .]*,\d{2})$",
    re.IGNORECASE,
)


class DeblockStatementParser(BaseParser):
    """Parses a Deblock account-statement PDF into transactions."""

    def parse(self, file_bytes: bytes) -> list[ParsedTransaction | UnparseableRow]:
        """
        Parse a Deblock statement PDF.

        :param file_bytes: the raw uploaded file.
        :raises UnrecognizedFormatError: if it isn't a readable PDF, isn't a
            Deblock account statement, or lacks the period line the rows'
            years are derived from. A single row that can't be read is an
            :class:`UnparseableRow` in the result instead.
        :return: every transaction row found, in statement order.
        """
        try:
            pdf = pdfplumber.open(io.BytesIO(file_bytes))
        except Exception as exc:
            raise UnrecognizedFormatError("Not a readable PDF file.") from exc
        with pdf:
            pages = list(pdf.pages)
            text = "\n".join(page.extract_text() or "" for page in pages)
            if "deblock" not in text.lower():
                raise UnrecognizedFormatError("Not a Deblock statement.")
            period = _PERIOD.search(text)
            if period is None:
                raise UnrecognizedFormatError("Missing the statement period line.")
            currency_match = _CURRENCY.search(text)
            currency = currency_match.group(1) if currency_match else "EUR"
            period_end = date(
                int(period.group(5)),
                _MONTHS[period.group(4).lower()],
                int(period.group(3)),
            )

            rows: list[ParsedTransaction | UnparseableRow] = []
            seen: defaultdict[str, int] = defaultdict(int)
            debit_x1: float | None = None
            credit_x1: float | None = None
            for page in pages:
                header_x = _column_edges(page)
                if header_x is not None:
                    debit_x1, credit_x1 = header_x
                for line_text, amount_x1 in _lines(page):
                    if not _ROW_START.match(line_text):
                        continue
                    rows.append(
                        _parse_row(
                            line_text,
                            amount_x1,
                            (debit_x1, credit_x1),
                            (period_end, currency, seen),
                        )
                    )
        return rows


def _column_edges(page: Page) -> tuple[float, float] | None:
    debit = credit = None
    for word in page.extract_words():
        if word["text"] == "Debit":
            debit = float(word["x1"])
        elif word["text"] == "Credit" and debit is not None:
            credit = float(word["x1"])
            break
    if debit is None or credit is None:
        return None
    return debit, credit


def _lines(page: Page) -> list[tuple[str, float]]:
    """Turn a page's lines into ``(line text, last word's right edge)``."""
    return [
        (" ".join(str(w["text"]) for w in line), float(line[-1]["x1"]))
        for line in group_lines(page)
    ]


def _resolve_date(day: str, month: str, period_end: date) -> date:
    month_number = _MONTHS[month.lower()]
    year = period_end.year if month_number <= period_end.month else period_end.year - 1
    return date(year, month_number, int(day))


def _parse_row(
    line_text: str,
    amount_x1: float,
    edges: tuple[float | None, float | None],
    context: tuple[date, str, defaultdict[str, int]],
) -> ParsedTransaction | UnparseableRow:
    period_end, currency, seen = context
    match = _ROW.match(line_text)
    debit_x1, credit_x1 = edges
    if match is None:
        return UnparseableRow(raw_text=line_text, reason="Unrecognized row layout.")
    if debit_x1 is None or credit_x1 is None:
        return UnparseableRow(raw_text=line_text, reason="No Debit/Credit header.")
    try:
        amount = Decimal(re.sub(r"[ .]", "", match["amount"]).replace(",", "."))
        occurred_at = _resolve_date(match["day"], match["month"], period_end)
        value_date = _resolve_date(match["vday"], match["vmonth"], period_end)
    except (InvalidOperation, ValueError) as exc:
        return UnparseableRow(raw_text=line_text, reason=str(exc))
    if abs(amount_x1 - debit_x1) <= abs(amount_x1 - credit_x1):
        amount = -amount
    counterparty = match["counterparty"].strip()
    description = f'{match["kind"].strip()} "{counterparty}"'
    base = f"deblock|{occurred_at}|{value_date}|{description}|{amount}"
    seen[base] += 1
    key = hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()
    return ParsedTransaction(
        dedupe_key=key,
        occurred_at=occurred_at,
        amount=amount,
        description=description,
        counterparty=counterparty or None,
        currency=currency,
    )
