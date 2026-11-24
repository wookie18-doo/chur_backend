# ruff: noqa: RUF001
from datetime import date
from decimal import Decimal
from typing import Any, Self

import pytest

from app.libs.parsers import revolut
from app.libs.parsers.base import (
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)
from app.libs.parsers.revolut import RevolutStatementParser

# Column left edges, as in a real export.
_DATE, _DESC, _CAT, _AMOUNT, _BAL = 39.7, 119.0, 243.9, 324.6, 378.9


def _w(text: str, x0: float, top: float) -> dict[str, Any]:
    return {"text": text, "x0": x0, "x1": x0 + 5 * len(text), "top": top}


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
    _w("Поступления", _AMOUNT, 239.4),
    _w("Дата", _DATE, 245.6),
    _w("Описание", _DESC, 245.6),
    _w("Категория", _CAT, 245.6),
    _w("Баланс", _BAL, 245.6),
]
_TEXT = "Revolut Bank UAB\nВыписка по операциям\nЛичный счет (EUR)"


def _row(
    top: float,
    description: str,
    category: str,
    amount: str,
    balance: str,
    day: str = "22",
) -> list[dict[str, Any]]:
    words = [
        _w(day, _DATE, top),
        _w("сент.", _DATE + 11, top),
        _w("2026г.", _DATE + 33, top),
    ]
    words += [
        _w(part, _DESC + 20 * i, top) for i, part in enumerate(description.split())
    ]
    words += [_w(part, _CAT + 20 * i, top) for i, part in enumerate(category.split())]
    words += [_w(amount, _AMOUNT, top), _w(balance, _BAL, top)]
    return words


def _parse(
    monkeypatch: pytest.MonkeyPatch, words: list[dict[str, Any]], text: str = _TEXT
) -> list[ParsedTransaction | UnparseableRow]:
    pdf = _FakePdf([_FakePage(words, text)])
    monkeypatch.setattr(revolut.pdfplumber, "open", lambda _stream: pdf)
    return RevolutStatementParser().parse(b"%PDF")


def test_parses_rows_signs_and_wrapped_descriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signed amounts, categories, and a wrapped second description line."""
    words = [
        *_HEADER,
        *_row(270.9, "Apple", "Торговая точка", "-6,49€", "12,35€"),
        *_row(302.0, "Перевод, получатель:", "Другое", "-1 028,00€", "18,84€"),
        _w("ANASTASIIA", _DESC, 314.4),
        _w("BLATNIK", _DESC + 60, 314.4),
        *_row(340.0, "Пополнение счета", "Пополнение", "47,00€", "66,84€", day="5"),
        _w("Итого", _DATE, 380.0),
    ]

    rows = _parse(monkeypatch, words)

    assert [r.amount for r in rows if isinstance(r, ParsedTransaction)] == [
        Decimal("-6.49"),
        Decimal("-1028.00"),
        Decimal("47.00"),
    ]
    first, transfer, topup = rows
    assert isinstance(first, ParsedTransaction)
    assert isinstance(transfer, ParsedTransaction)
    assert isinstance(topup, ParsedTransaction)
    assert first.occurred_at == date(2026, 9, 22)
    assert first.currency == "EUR"
    assert first.counterparty == "Apple"
    assert transfer.description == "Перевод, получатель: ANASTASIIA BLATNIK"
    assert transfer.counterparty == "ANASTASIIA BLATNIK"
    assert topup.occurred_at == date(2026, 9, 5)
    assert topup.counterparty is None


def test_identical_rows_get_distinct_stable_dedupe_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two identical rows are both kept; keys are stable across parses."""
    words = [
        *_HEADER,
        *_row(270.9, "Apple", "Торговая точка", "-6,49€", "12,35€"),
        *_row(300.0, "Apple", "Торговая точка", "-6,49€", "12,35€"),
    ]

    first = _parse(monkeypatch, words)
    second = _parse(monkeypatch, words)

    keys = [r.dedupe_key for r in first if isinstance(r, ParsedTransaction)]
    assert len(set(keys)) == 2
    assert keys == [r.dedupe_key for r in second if isinstance(r, ParsedTransaction)]


def test_bad_amount_is_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row with an unreadable amount doesn't sink the file."""
    words = [
        *_HEADER,
        *_row(270.9, "Apple", "Торговая точка", "n/a", "12,35€"),
        *_row(300.0, "Mercator", "Торговая точка", "-7,77€", "1,08€"),
    ]

    rows = _parse(monkeypatch, words)

    assert isinstance(rows[0], UnparseableRow)
    assert isinstance(rows[1], ParsedTransaction)


def test_other_provider_pdf_is_unrecognized(monkeypatch: pytest.MonkeyPatch) -> None:
    """A PDF without Revolut's markers is rejected."""
    with pytest.raises(UnrecognizedFormatError):
        _parse(monkeypatch, [], text="Some other bank")


def test_non_pdf_is_unrecognized() -> None:
    """Bytes that aren't a PDF raise UnrecognizedFormatError."""
    with pytest.raises(UnrecognizedFormatError):
        RevolutStatementParser().parse(b"not a pdf")
