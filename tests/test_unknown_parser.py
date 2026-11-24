import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.libs.parsers.base import (
    BaseParser,
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
    UnsupportedContentTypeError,
)
from app.libs.parsers.unknown import UnknownParser


class _FakeClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages: list[dict[str, Any]] = []

    async def complete_json(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        self.messages = messages
        return self.reply


def _parser(reply: object) -> tuple[UnknownParser, _FakeClient]:
    text = reply if isinstance(reply, str) else json.dumps(reply)
    client = _FakeClient(text)
    return UnknownParser(client), client  # type: ignore[arg-type]


async def test_wraps_rows_in_models() -> None:
    """Valid rows become ParsedTransaction, bad ones UnparseableRow."""
    parser, client = _parser(
        {
            "transactions": [
                {
                    "id": "tx1",
                    "date": "2026-03-01",
                    "amount": "-12.50",
                    "currency": "eur",
                    "description": "Coffee",
                    "counterparty": "Cafe",
                },
                {"date": "bad", "amount": "1", "currency": "EUR"},
            ],
            "unparseable": [{"raw_text": "smudged", "reason": "blurry"}],
        }
    )

    rows = await parser.parse(b"date,amount\n2026-03-01,-12.50\n")

    assert isinstance(parser, BaseParser)
    assert rows[0] == ParsedTransaction(
        dedupe_key="tx1",
        occurred_at=date(2026, 3, 1),
        amount=Decimal("-12.50"),
        description="Coffee",
        counterparty="Cafe",
        currency="EUR",
    )
    assert isinstance(rows[1], UnparseableRow)
    assert rows[2] == UnparseableRow(raw_text="smudged", reason="blurry")
    assert client.messages[1]["content"][1]["type"] == "text"


async def test_fenced_json_is_accepted() -> None:
    """A reply wrapped in a markdown fence still parses."""
    parser, _ = _parser('```json\n{"transactions": []}\n```')

    assert await parser.parse(b"x") == []


async def test_bad_reply_is_unrecognized() -> None:
    """A non-JSON or shapeless reply raises UnrecognizedFormatError."""
    for reply in ("not json", {"foo": 1}):
        parser, _ = _parser(reply)
        with pytest.raises(UnrecognizedFormatError):
            await parser.parse(b"x")


async def test_binary_file_is_unsupported() -> None:
    """Files that are neither PDF, image nor text are rejected."""
    parser, _ = _parser({"transactions": []})

    with pytest.raises(UnsupportedContentTypeError):
        await parser.parse(b"\x00\x01\x02binary")
