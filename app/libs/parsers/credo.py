"""
Credo Bank (MyCredo) account-statement PDF parser.

Built against MyCredo's bilingual Georgian/English "Account Statement"
PDF (text layer). The bank's name isn't in the text at all, so the file is
recognized by its English table header plus a Credo IBAN (bank code
``CD``). Each page after the summary repeats a ``Date | Operation |
Turnover (DB) | Turnover (Cr) | Balance | Description | Beneficiary Name |
Beneficiary Account`` table whose cells wrap onto lines above *and* below
the row's date, so every word is assigned to the row whose date line is
vertically nearest, then to a column by its horizontal position under the
page's own header. Amounts carry no sign: the debit/credit column decides
it. A card payment's own date (inside its description) is used instead of
the posting date. The export has no per-row id, so ``dedupe_key`` is a
hash that includes the running balance and the row's occurrence number.
"""

import hashlib
import io
import re
from collections import defaultdict
from datetime import date, datetime
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

_CREDO_IBAN = re.compile(r"\bGE\d{2}CD\d{16}\b")
_CURRENCY = re.compile(r"ანგარიშის ვალუტა:\s*([A-Z]{3})\b")
_DATE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_AMOUNT = re.compile(r"^\d{1,3}(?:,\d{3})*\.\d{2}$")
_CARD = re.compile(
    r"^\S+ - (?P<merchant>.+?) \d[\d,]*\.\d{2} [A-Z]{3} "
    r"(?P<date>\d{2}\.\d{2}\.\d{4})$"
)
_HEADER_WORDS = frozenset({"Date", "Operation", "Balance", "Description", "Name"})
#: How far (pt) a wrapped cell line may sit from its row's date line.
_MAX_ROW_DISTANCE = 25.0
_TOLERANCE = 6.0


class CredoStatementParser(BaseParser):
    """Parses a Credo Bank account-statement PDF into transactions."""

    def parse(self, file_bytes: bytes) -> list[ParsedTransaction | UnparseableRow]:
        """
        Parse a Credo Bank statement PDF.

        :param file_bytes: the raw uploaded file.
        :raises UnrecognizedFormatError: if it isn't a readable PDF or isn't a
            Credo account statement. A single row that can't be read is an
            :class:`UnparseableRow` in the result instead.
        :return: every transaction row found, in statement order.
        """
        try:
            pdf = pdfplumber.open(io.BytesIO(file_bytes))
        except Exception as exc:
            raise UnrecognizedFormatError("Not a readable PDF file.") from exc
        with pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if (
                "Account Statement" not in text
                or "Turnover (DB)" not in text
                or _CREDO_IBAN.search(text) is None
            ):
                raise UnrecognizedFormatError("Not a Credo Bank statement.")
            currency_match = _CURRENCY.search(text)
            currency = currency_match.group(1) if currency_match else "EUR"

            rows: list[ParsedTransaction | UnparseableRow] = []
            seen: defaultdict[str, int] = defaultdict(int)
            for page in pdf.pages:
                for cells in _page_rows(page):
                    rows.append(_build(cells, currency, seen))
        return rows


def _span(words: list[dict[str, Any]]) -> tuple[float, float]:
    return float(words[0]["x0"]), float(words[-1]["x1"])


def _center(word: dict[str, Any]) -> float:
    return (float(word["x0"]) + float(word["x1"])) / 2


def _layout(line: list[dict[str, Any]]) -> dict[str, float] | None:
    """Column geometry from the English header line, if ``line`` is it."""
    texts = [str(w["text"]) for w in line]
    beneficiary = [w for w in line if w["text"] == "Beneficiary"]
    if (
        not set(texts) >= _HEADER_WORDS
        or texts.count("Turnover") != 2
        or len(beneficiary) != 2
    ):
        return None
    turnovers = [i for i, text in enumerate(texts) if text == "Turnover"]
    debit = _span(line[turnovers[0] : turnovers[0] + 2])
    credit = _span(line[turnovers[1] : turnovers[1] + 2])
    balance = next(w for w in line if w["text"] == "Balance")
    description = next(w for w in line if w["text"] == "Description")
    name_end = next(w for w in line if w["text"] == "Name")
    operation = next(w for w in line if w["text"] == "Operation")
    return {
        "operation_start": float(operation["x0"]),
        "operation_end": float(operation["x1"]),
        "debit": sum(debit) / 2,
        "credit": sum(credit) / 2,
        "balance": _center(balance),
        "text_start": float(balance["x1"]) + _TOLERANCE,
        "name_start": (float(description["x1"]) + float(beneficiary[0]["x0"])) / 2,
        "account_start": (float(name_end["x1"]) + float(beneficiary[1]["x0"])) / 2,
    }


def _page_rows(page: Any) -> list[dict[str, list[str]]]:
    """Split one page's table into rows of column -> words."""
    layout = None
    body: list[dict[str, Any]] = []
    for line in group_lines(page):
        if layout is None:
            layout = _layout(line)
            continue
        body.extend(line)
    if layout is None:
        return []
    anchors = [
        w
        for w in body
        if _DATE.match(str(w["text"])) and float(w["x1"]) < layout["operation_start"]
    ]
    if not anchors:
        return []
    rows: list[dict[str, list[str]]] = [defaultdict(list) for _ in anchors]
    for index, anchor in enumerate(anchors):
        rows[index]["date"].append(str(anchor["text"]))
    anchor_ids = {id(a) for a in anchors}
    for word in sorted(body, key=lambda w: (float(w["top"]), float(w["x0"]))):
        if id(word) in anchor_ids:
            continue
        top = float(word["top"])
        index = min(
            range(len(anchors)),
            key=lambda i: abs(float(anchors[i]["top"]) - top),
        )
        if abs(float(anchors[index]["top"]) - top) > _MAX_ROW_DISTANCE:
            continue
        rows[index][_column(word, layout)].append(str(word["text"]))
    return rows


def _column(word: dict[str, Any], layout: dict[str, float]) -> str:
    center = _center(word)
    text = str(word["text"])
    if center < layout["text_start"]:
        if _AMOUNT.match(text) and center > layout["operation_end"]:
            return min(
                ("debit", "credit", "balance"),
                key=lambda column: abs(layout[column] - center),
            )
        return "operation"
    x0 = float(word["x0"])
    if x0 < layout["name_start"]:
        return "description"
    if x0 < layout["account_start"]:
        return "name"
    return "account"


def _money(raw: str) -> Decimal:
    return Decimal(raw.replace(",", ""))


def _build(
    cells: dict[str, list[str]], currency: str, seen: defaultdict[str, int]
) -> ParsedTransaction | UnparseableRow:
    def joined(column: str) -> str:
        return " ".join(cells.get(column, [])).strip()

    raw_text = " | ".join(
        joined(column)
        for column in (
            "date",
            "operation",
            "debit",
            "credit",
            "balance",
            "description",
            "name",
            "account",
        )
    )
    debit, credit = cells.get("debit", []), cells.get("credit", [])
    if len(debit) + len(credit) != 1 or len(cells.get("balance", [])) != 1:
        return UnparseableRow(
            raw_text=raw_text, reason="Expected one amount and one balance."
        )
    try:
        posted_at = _parse_date(joined("date"))
        amount = -_money(debit[0]) if debit else _money(credit[0])
        balance = _money(joined("balance"))
    except (ValueError, InvalidOperation) as exc:
        return UnparseableRow(raw_text=raw_text, reason=str(exc))

    operation, details = joined("operation"), joined("description")
    counterparty = joined("name") or None
    occurred_at = posted_at
    description = f"{operation}: {details}" if details else operation
    card = _CARD.match(details)
    if card is not None:
        counterparty = card["merchant"]
        description = f"{operation}: {counterparty}"
        try:
            occurred_at = _parse_date(card["date"])
        except ValueError:
            occurred_at = posted_at
    base = f"credo|{posted_at}|{operation}|{details}|{amount}|{balance}"
    seen[base] += 1
    key = hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()
    return ParsedTransaction(
        dedupe_key=key,
        occurred_at=occurred_at,
        amount=amount,
        description=description,
        counterparty=counterparty,
        currency=currency,
    )


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%d.%m.%Y").date()
