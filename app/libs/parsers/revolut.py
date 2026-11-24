"""
Revolut account-statement PDF parser.

Built against Revolut's Russian-language "Индивидуальная выписка" PDF
(text layer) -- **only that locale is verified**; another language's
export (different month names and headings) raises
``UnrecognizedFormatError`` rather than being guessed at. Each page's
operations table has the columns ``Дата | Описание | Категория |
Поступления / Списания | Баланс | ...``; columns are told apart by their
header's horizontal position, and a long description wraps onto the lines
below its row. The export has no per-row id, so ``dedupe_key`` is a hash
that includes the running balance and the row's occurrence number.
"""

import hashlib
import io
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pdfplumber

from app.libs.parsers.base import (
    BaseParser,
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)
from app.libs.parsers.pdf import group_lines

_MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}
_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
_DAY = re.compile(r"^\d{1,2}$")
_YEAR = re.compile(r"^(\d{4})\u0433\.?$")
_MONEY = re.compile(
    r"^(?P<sign>[-+\u2212])?(?P<number>\d[\d\s\u00a0]*[.,]\d{2})(?P<cur>\D)$"
)
_SECTION_CURRENCY = re.compile(r"\(([A-Z]{3})\)")
_TOLERANCE = 2.0
_MIN_DATE_WORDS = 3


class RevolutStatementParser(BaseParser):
    """Parses a Revolut account-statement PDF into transactions."""

    def parse(self, file_bytes: bytes) -> list[ParsedTransaction | UnparseableRow]:
        """
        Parse a Revolut statement PDF.

        :param file_bytes: the raw uploaded file.
        :raises UnrecognizedFormatError: if it isn't a readable PDF or isn't a
            (Russian-language) Revolut account statement. A single row that
            can't be read is an :class:`UnparseableRow` in the result instead.
        :return: every transaction row found, in statement order.
        """
        try:
            pdf = pdfplumber.open(io.BytesIO(file_bytes))
        except Exception as exc:
            raise UnrecognizedFormatError("Not a readable PDF file.") from exc
        with pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if "revolut" not in text.lower() or "Выписка по операциям" not in text:
                raise UnrecognizedFormatError("Not a Revolut statement.")
            currency_match = _SECTION_CURRENCY.search(text)
            currency = currency_match.group(1) if currency_match else "EUR"

            rows: list[ParsedTransaction | UnparseableRow] = []
            seen: defaultdict[str, int] = defaultdict(int)
            for page in pdf.pages:
                currency = _parse_page(page, currency, seen, rows)
        return rows


def _columns(line: list[dict[str, Any]]) -> dict[str, float] | None:
    left = {str(w["text"]): float(w["x0"]) for w in line}
    if not {"Дата", "Описание", "Категория", "Баланс"} <= left.keys():
        return None
    return {
        "date": left["Дата"],
        "description": left["Описание"],
        "category": left["Категория"],
        "balance": left["Баланс"],
    }


def _parse_page(
    page: Any,
    currency: str,
    seen: defaultdict[str, int],
    rows: list[ParsedTransaction | UnparseableRow],
) -> str:
    """Parse one page's operations table into ``rows``; return the currency."""
    columns: dict[str, float] | None = None
    amount_x0 = next(
        (float(w["x0"]) for w in page.extract_words() if w["text"] == "Поступления"),
        None,
    )
    pending: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            rows.append(_build(pending, seen))
            pending = None

    for line in group_lines(page):
        found = _columns(line)
        if found is not None:
            columns = found
            flush()
            continue
        words = {str(w["text"]) for w in line}
        if columns is None:
            section = _SECTION_CURRENCY.search(" ".join(w["text"] for w in line))
            if section and "счет" in words:
                currency = section.group(1)
            continue
        if amount_x0 is None:
            continue
        in_description = all(
            columns["description"] - _TOLERANCE
            <= float(w["x0"])
            < columns["category"] - _TOLERANCE
            for w in line
        )
        if in_description and pending is not None:
            pending["description"].append(_join(line))
            pending["raw"].append(_join(line))
            continue
        flush()
        if _starts_row(line, columns):
            pending = _collect(line, columns, amount_x0, currency)
    flush()
    return currency


def _join(words: list[dict[str, Any]]) -> str:
    return " ".join(str(w["text"]) for w in words)


def _starts_row(line: list[dict[str, Any]], columns: dict[str, float]) -> bool:
    date_words = [
        w for w in line if float(w["x0"]) < columns["description"] - _TOLERANCE
    ]
    return len(date_words) >= _MIN_DATE_WORDS and bool(
        _DAY.match(str(date_words[0]["text"]))
    )


def _collect(
    line: list[dict[str, Any]],
    columns: dict[str, float],
    amount_x0: float,
    currency: str,
) -> dict[str, Any]:
    def between(low: float, high: float) -> list[dict[str, Any]]:
        return [
            w for w in line if low - _TOLERANCE <= float(w["x0"]) < high - _TOLERANCE
        ]

    return {
        "date": [str(w["text"]) for w in between(0, columns["description"])],
        "description": [_join(between(columns["description"], columns["category"]))],
        "category": _join(between(columns["category"], amount_x0)),
        "amount": "".join(
            str(w["text"]) for w in between(amount_x0, columns["balance"])
        ),
        "balance": str(
            next(iter(between(columns["balance"], 10_000)), {"text": ""})["text"]
        ),
        "currency": currency,
        "raw": [_join(line)],
    }


def _money(raw: str) -> tuple[Decimal, str]:
    match = _MONEY.match(raw.strip())
    if match is None:
        raise ValueError(f"Unrecognized amount: {raw!r}")
    number = re.sub(r"[\s\u00a0]", "", match["number"]).replace(",", ".")
    value = Decimal(number)
    return (-value if match["sign"] in ("-", "\u2212") else value), match["cur"]


def _build(
    pending: dict[str, Any], seen: defaultdict[str, int]
) -> ParsedTransaction | UnparseableRow:
    raw_text = "\n".join(pending["raw"])
    try:
        day, month_word, year_word = pending["date"][:3]
        year = _YEAR.match(year_word)
        month = _MONTHS.get(month_word.lower()[:3])
        if year is None or month is None:
            raise ValueError(f"Unrecognized date: {' '.join(pending['date'])!r}")
        occurred_at = date(int(year.group(1)), month, int(day))
        amount, symbol = _money(pending["amount"])
        balance, _ = _money(pending["balance"])
    except (ValueError, InvalidOperation) as exc:
        return UnparseableRow(raw_text=raw_text, reason=str(exc))
    description = " ".join(pending["description"]).strip()
    base = f"revolut|{occurred_at}|{description}|{amount}|{balance}"
    seen[base] += 1
    key = hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()
    return ParsedTransaction(
        dedupe_key=key,
        occurred_at=occurred_at,
        amount=amount,
        description=description,
        counterparty=_counterparty(description, pending["category"]),
        currency=_SYMBOLS.get(symbol, pending["currency"]),
    )


def _counterparty(description: str, category: str) -> str | None:
    transfer = re.match(r"^Перевод, (?:получатель|отправитель):\s*(.+)$", description)
    if transfer:
        return transfer.group(1).strip()
    if category.strip() == "Торговая точка":
        return description or None
    return None
