from datetime import date
from decimal import Decimal
from typing import Any, Self

import pytest

from app.libs.parsers import credo
from app.libs.parsers.base import (
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)
from app.libs.parsers.credo import CredoStatementParser
from app.libs.parsers.registry import StatementParser

# Column positions, as in a real export.
_DEBIT, _CREDIT, _BALANCE, _DESC, _NAME, _ACCOUNT = 229, 302, 362, 400, 555, 675
_TEXT = (
    "Account Statement\nGE96CD0360000045416658\n"
    "Date Operation Turnover (DB) Turnover (Cr) Balance Description"
)


def _w(text: str, x0: float, top: float, x1: float | None = None) -> dict[str, Any]:
    return {"text": text, "x0": x0, "x1": x1 or x0 + 5 * len(text), "top": top}


def _centered(text: str, center: float, top: float) -> dict[str, Any]:
    half = 2.5 * len(text)
    return _w(text, center - half, top, center + half)


def _phrase(text: str, x0: float, top: float) -> list[dict[str, Any]]:
    words = []
    for part in text.split():
        words.append(_w(part, x0, top))
        x0 += 5 * len(part) + 3
    return words


class _FakePage:
    def __init__(self, words: list[dict[str, Any]], text: str) -> None:
        self._words = words
        self._text = text

    def extract_words(self) -> list[dict[str, Any]]:
        return self._words

    def extract_text(self) -> str:
        return self._text


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


_HEADER = [
    _w("Date", 55.8, 73.4, 77.4),
    _w("Operation", 120.7, 73.4, 167.3),
    _w("Turnover", 197.2, 73.4, 239.1),
    _w("(DB)", 241.7, 73.4, 261.0),
    _w("Turnover", 272.2, 73.4, 314.1),
    _w("(Cr)", 316.6, 73.4, 332.6),
    _w("Balance", 344.5, 73.4, 380.5),
    _w("Description", 436.8, 73.4, 489.2),
    _w("Beneficiary", 563.5, 73.4, 614.4),
    _w("Name", 616.9, 73.4, 644.4),
    _w("Beneficiary", 692.0, 73.4, 742.9),
    _w("Account", 745.5, 73.4, 782.5),
]


def _transfer(
    top: float, day: str, amount: str, balance: str, *, credit: bool
) -> list[dict[str, Any]]:
    return [
        *_phrase("Transfer between", 103.6, top - 13.2),
        _w(day, 41.6, top, 91.5),
        *_phrase("your own", 122.5, top),
        _centered(amount, _CREDIT if credit else _DEBIT, top),
        _centered(balance, _BALANCE, top),
        *_phrase("Personal Transfer", 422.5, top),
        *_phrase("John Doe", _NAME, top),
        _w("GE55CD0360000045430685", _ACCOUNT, top),
        _w("accounts", 123.5, top + 13.3),
    ]


def _card(
    top: float, posted: str, amount: str, balance: str, details: list[str]
) -> list[dict[str, Any]]:
    words = [
        _w(posted, 41.6, top, 91.5),
        *_phrase("Card operation", 109.5, top),
        _centered(amount, _DEBIT, top),
        _centered(balance, _BALANCE, top),
    ]
    for offset, line in zip((-6.6, 6.6, 13.2), details, strict=False):
        words += _phrase(line, _DESC, top + offset)
    return words


def _parse(
    monkeypatch: pytest.MonkeyPatch,
    words: list[dict[str, Any]],
    text: str = _TEXT,
) -> list[ParsedTransaction | UnparseableRow]:
    summary = _FakePage([_w("Account", 200.7, 100.5)], text)
    pdf = _FakePdf([summary, _FakePage(words, "")])
    monkeypatch.setattr(credo.pdfplumber, "open", lambda _stream: pdf)
    return CredoStatementParser().parse(b"%PDF")


def test_parses_transfers_and_card_payments(monkeypatch: pytest.MonkeyPatch) -> None:
    """Columns decide the sign; wrapped cells join; card date wins."""
    words = [
        *_HEADER,
        *_transfer(110.4, "28.11.2024", "1,325.00", "1,325.00", credit=True),
        *_transfer(160.7, "28.11.2024", "325.00", "1,000.00", credit=False),
        *_card(
            211.0,
            "05.12.2024",
            "129.00",
            "871.00",
            ["Payment - IKEA Slovenia", "online 129.00 EUR", "04.12.2024"],
        ),
    ]

    rows = _parse(monkeypatch, words)

    assert all(isinstance(r, ParsedTransaction) for r in rows)
    incoming, outgoing, card = rows
    assert isinstance(incoming, ParsedTransaction)
    assert isinstance(outgoing, ParsedTransaction)
    assert isinstance(card, ParsedTransaction)
    assert incoming.amount == Decimal("1325.00")
    assert incoming.occurred_at == date(2024, 11, 28)
    assert incoming.description == (
        "Transfer between your own accounts: Personal Transfer"
    )
    assert incoming.counterparty == "John Doe"
    assert incoming.currency == "EUR"
    assert outgoing.amount == Decimal("-325.00")
    assert card.amount == Decimal("-129.00")
    assert card.occurred_at == date(2024, 12, 4)
    assert card.counterparty == "IKEA Slovenia online"
    assert card.description == "Card operation: IKEA Slovenia online"


def test_identical_rows_get_distinct_dedupe_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two genuinely identical rows are both kept, with distinct keys."""
    row = _transfer(110.4, "28.11.2024", "5.00", "5.00", credit=True)
    words = [*_HEADER, *row, *[{**w, "top": w["top"] + 50} for w in row]]

    rows = _parse(monkeypatch, words)

    keys = {r.dedupe_key for r in rows if isinstance(r, ParsedTransaction)}
    assert len(keys) == 2


def test_row_without_amount_is_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row missing its turnover doesn't sink the file."""
    words = [
        *_HEADER,
        _w("28.11.2024", 41.6, 110.4, 91.5),
        _centered("5.00", _BALANCE, 110.4),
    ]

    rows = _parse(monkeypatch, words)

    assert len(rows) == 1
    assert isinstance(rows[0], UnparseableRow)


def test_other_bank_statement_is_unrecognized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A statement without a Credo IBAN is rejected."""
    text = _TEXT.replace("CD", "BG")
    with pytest.raises(UnrecognizedFormatError):
        _parse(monkeypatch, _HEADER, text)


@pytest.mark.parametrize("payload", [b"not a pdf", b""])
def test_non_pdf_is_unrecognized(payload: bytes) -> None:
    """Bytes that aren't a PDF raise UnrecognizedFormatError."""
    with pytest.raises(UnrecognizedFormatError):
        CredoStatementParser().parse(payload)


def test_registry_maps_credo_code() -> None:
    """The ``Credo`` source's code picks this parser."""
    assert isinstance(StatementParser("credo").parser, CredoStatementParser)
