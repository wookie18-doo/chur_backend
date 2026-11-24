from datetime import date
from decimal import Decimal

import pytest

from app.libs.parsers.base import (
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)
from app.libs.parsers.deblock import DeblockStatementParser

_DEBIT_X = 424.0
_CREDIT_X = 464.0


def _pdf(items: list[tuple[float, float, str]]) -> bytes:
    """Build a one-page text-layer PDF; items are ``(right_x, y, text)``."""
    parts = ["BT", "/F1 8 Tf"]
    for right_x, y, text in items:
        width = 0.5 * 8 * len(text)
        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        parts.append(f"1 0 0 1 {right_x - width:.2f} {y} Tm ({escaped}) Tj")
    parts.append("ET")
    content = "\n".join(parts).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
            b"/MediaBox [0 0 595 842] /Contents 4 0 R >>"
        ),
        (b"<< /Length %d >>\nstream\n" % len(content)) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    buf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        buf += f"{offset:010d} 00000 n \n".encode()
    buf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    ).encode()
    return bytes(buf)


def _row(
    y: float, text: str, amount: str, *, credit: bool = False
) -> list[tuple[float, float, str]]:
    return [
        (10 + 0.5 * 8 * len(text), y, text),
        (_CREDIT_X if credit else _DEBIT_X, y, amount),
    ]


def _statement(rows: list[list[tuple[float, float, str]]]) -> bytes:
    head = [
        (80.0, 800.0, "EUR Account Statement"),
        (
            200.0,
            780.0,
            "Account transactions from 1 November 2026 to 19 November 2026",
        ),
        (_DEBIT_X, 760.0, "Debit"),
        (_CREDIT_X, 760.0, "Credit"),
        (60.0, 40.0, "Deblock SAS"),
    ]
    items = head + [item for row in rows for item in row]
    return _pdf(items)


def test_parses_debits_and_credits() -> None:
    """The amount's column decides its sign; dates get the period's year."""
    pdf = _statement(
        [
            _row(740, '1 November 31 October Card Payment "VOLI"', "3,99"),
            _row(
                725,
                '2 November 2 November Transfer "Some Person"',
                "1 100,00",
                credit=True,
            ),
        ]
    )

    rows = DeblockStatementParser().parse(pdf)

    assert [type(r) for r in rows] == [ParsedTransaction, ParsedTransaction]
    first, second = rows
    assert isinstance(first, ParsedTransaction)
    assert isinstance(second, ParsedTransaction)
    assert first.occurred_at == date(2026, 11, 1)
    assert first.amount == Decimal("-3.99")
    assert first.description == 'Card Payment "VOLI"'
    assert first.counterparty == "VOLI"
    assert first.currency == "EUR"
    assert second.amount == Decimal("1100.00")


def test_identical_rows_get_distinct_dedupe_keys() -> None:
    """Two genuinely identical rows are both kept, with stable distinct keys."""
    row = '3 November 2 November Card Payment "Dodo Pizza"'
    pdf = _statement([_row(740, row, "9,00"), _row(725, row, "9,00")])

    first = DeblockStatementParser().parse(pdf)
    second = DeblockStatementParser().parse(pdf)

    keys = [r.dedupe_key for r in first if isinstance(r, ParsedTransaction)]
    assert len(set(keys)) == 2
    assert keys == [r.dedupe_key for r in second if isinstance(r, ParsedTransaction)]


def test_unreadable_row_is_unparseable() -> None:
    """A row-shaped line that doesn't fit the layout doesn't sink the file."""
    pdf = _statement([_row(740, "4 November garbled row", "1,00")])

    rows = DeblockStatementParser().parse(pdf)

    assert len(rows) == 1
    assert isinstance(rows[0], UnparseableRow)


@pytest.mark.parametrize("payload", [b"not a pdf", b""])
def test_non_pdf_is_unrecognized(payload: bytes) -> None:
    """Bytes that aren't a PDF raise UnrecognizedFormatError."""
    with pytest.raises(UnrecognizedFormatError):
        DeblockStatementParser().parse(payload)


def test_other_provider_pdf_is_unrecognized() -> None:
    """A PDF without Deblock's markers is rejected."""
    pdf = _pdf([(100.0, 700.0, "Some other bank statement")])

    with pytest.raises(UnrecognizedFormatError):
        DeblockStatementParser().parse(pdf)
