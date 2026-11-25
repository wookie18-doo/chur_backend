from datetime import date
from decimal import Decimal

import pytest

from app.libs.parsers.base import (
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
)
from app.libs.parsers.nexo import NexoStatementParser
from app.libs.parsers.registry import StatementParser

_HEADER = (
    "Transaction,Type,Credit Line,Input Currency,Input Amount,Output Currency,"
    "Output Amount,USD Equivalent,Fee,Fee Currency,Details,Date / Time (UTC)"
)


def _csv(*rows: str) -> bytes:
    return "\n".join((_HEADER, *rows)).encode()


def test_imports_only_card_rows() -> None:
    """Purchases, refunds and fees are kept; wallet bookkeeping is skipped."""
    payload = _csv(
        "NXT1,Exchange,,USDC,-27.64,EURX,24.90000000,$27.22,-,-,"
        '"approved / Nexo Card / Exchange USD Coin to EURX",2026-11-25 11:57:22',
        "NXT2,Credit Card Fiatx Exchange To Withdraw,,EURX,-24.90,EUR,24.90,"
        '$27.22,-,-,"authorized / EUR",2026-11-25 11:57:19',
        "NXT3,Nexo Card Purchase,,USD,-27.22,EUR,24.90000000,$27.22,-,-,"
        '"authorized / MCDONALDS RUDNIK | LJUBLJANA | SVN",2026-11-25 11:57:19',
        "NXT4,Interest,Classic,xUSD,-0.46,xUSD,0.46000000,$0.46,-,-,"
        '"approved / Interest",2026-11-25 00:00:00',
        "NXT5,Withdraw Exchanged,,EUR,-61.47,EUR,61.47000000,$67.26,-,-,"
        '"approved / EUR withdrawal",2026-11-24 01:40:20',
        "NXT6,Nexo Card Transaction Fee,,USD,-0.30,EUR,0.27000000,$0.30,-,-,"
        '"approved / 2% Weekday FX Fee",2026-11-16 20:07:11',
        "NXT7,Nexo Card Refund,,EUR,7.37,EUR,7.37000000,$8.24,-,-,"
        '"approved / AMAZON* NN5GL9VR4 | LUXEMBOURG | LUX",2026-10-29 16:52:57',
        "NXT8,Top up Crypto,,USDT,199.94,USDT,199.94350000,$199.72,-,-,"
        '"approved / 0xe4a0",2026-11-10 19:36:44',
    )

    rows = NexoStatementParser().parse(payload)

    assert all(isinstance(r, ParsedTransaction) for r in rows)
    purchase, fee, refund = rows
    assert isinstance(purchase, ParsedTransaction)
    assert isinstance(fee, ParsedTransaction)
    assert isinstance(refund, ParsedTransaction)
    assert purchase.dedupe_key == "NXT3"
    assert purchase.occurred_at == date(2026, 11, 25)
    assert purchase.amount == Decimal("-24.90")
    assert purchase.currency == "EUR"
    assert purchase.description == "MCDONALDS RUDNIK | LJUBLJANA | SVN"
    assert purchase.counterparty == "MCDONALDS RUDNIK"
    assert fee.amount == Decimal("-0.27")
    assert fee.description == "2% Weekday FX Fee"
    assert fee.counterparty is None
    assert refund.amount == Decimal("7.37")
    assert refund.counterparty == "AMAZON* NN5GL9VR4"


def test_rejected_rows_are_skipped() -> None:
    """A declined card purchase never moved money."""
    payload = _csv(
        "NXT1,Nexo Card Purchase,,USD,-22.72,EUR,20.55000000,$22.73,-,-,"
        '"rejected / SAMOPOSTREZBA MURGLE | LJUBLJANA | SVN",2026-11-13 07:14:23',
    )

    assert NexoStatementParser().parse(payload) == []


def test_bad_card_row_is_unparseable() -> None:
    """One unreadable card row doesn't sink the file."""
    payload = _csv(
        "NXT1,Nexo Card Purchase,,USD,-1,EUR,oops,$1,-,-,"
        '"approved / SHOP",2026-11-13 07:14:23',
        "NXT2,Nexo Card Purchase,,USD,-1,EUR,1.00,$1,-,-,"
        '"approved / SHOP",2026-11-13 07:14:23',
    )

    bad, good = NexoStatementParser().parse(payload)

    assert isinstance(bad, UnparseableRow)
    assert isinstance(good, ParsedTransaction)


@pytest.mark.parametrize(
    "payload", [b"", b"Date,Amount,Description\n2026-01-01,1,x", b"\xff\xfe"]
)
def test_other_files_are_unrecognized(payload: bytes) -> None:
    """Anything without Nexo's columns raises UnrecognizedFormatError."""
    with pytest.raises(UnrecognizedFormatError):
        NexoStatementParser().parse(payload)


def test_registry_maps_nexo_code() -> None:
    """The ``Nexo`` source's code picks this parser."""
    assert isinstance(StatementParser("nexo").parser, NexoStatementParser)
