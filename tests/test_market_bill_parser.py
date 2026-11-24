import io
import json
from typing import Any

import pytest
from PIL import Image
from pillow_heif import register_heif_opener

from app.libs.parsers.base import (
    UnrecognizedFormatError,
    UnsupportedContentTypeError,
)
from app.libs.parsers.market_bill import MarketBillParser
from tests.test_imports import _make_text_pdf

register_heif_opener()

_REPLY = {
    "merchant": "Lidl",
    "date": "2026-01-15",
    "total": "4.37",
    "items": [
        {"name": "Milk 1 L", "amount": "2.38", "quantity": None},
        {"name": "Bananas", "amount": "1.99", "quantity": "1.2 kg"},
        {"name": "Discount", "amount": "-0.50", "quantity": None},
    ],
}


class _FakeClient:
    def __init__(self, reply: object = _REPLY) -> None:
        self.reply = json.dumps(reply)
        self.calls: list[list[dict[str, Any]]] = []

    async def complete_json(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        self.calls.append(messages)
        return self.reply

    def sent_part(self) -> dict[str, Any]:
        part: dict[str, Any] = self.calls[0][1]["content"][1]
        return part


def _image(fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (80, 120), "white").save(buffer, fmt)
    return buffer.getvalue()


def _parser(client: _FakeClient) -> MarketBillParser:
    return MarketBillParser(client)  # type: ignore[arg-type]


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "HEIF"])
async def test_photo_goes_to_the_model_as_jpeg(fmt: str) -> None:
    """PNG/JPEG/WebP/HEIC photos are re-encoded as JPEG and parsed by the LLM."""
    client = _FakeClient()

    bill = await _parser(client).parse(_image(fmt), "application/octet-stream")

    assert client.sent_part()["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert bill.merchant == "Lidl"
    assert [item.name for item in bill.items] == ["Milk 1 L", "Bananas"]
    assert bill.items[1].quantity == "1.2 kg"
    assert str(bill.total_amount) == "4.37"
    assert bill.purchased_at is not None


async def test_image_only_pdf_goes_to_the_model_as_a_file() -> None:
    """A PDF with no text layer is handed to the model as-is."""
    client = _FakeClient()

    bill = await _parser(client).parse(_image("PDF"))

    assert client.sent_part()["type"] == "file"
    assert len(bill.items) == 2


async def test_text_pdf_skips_the_model() -> None:
    """A readable text-layer PDF is parsed by the heuristic, free of charge."""
    client = _FakeClient()
    pdf = _make_text_pdf(["Lidl", "2026-01-15", "Milk 1 L    2.38", "Total    2.38"])

    bill = await _parser(client).parse(pdf)

    assert client.calls == []
    assert bill.items[0].name == "Milk 1 L"


async def test_unrecognised_text_pdf_falls_back_to_the_model() -> None:
    """A text PDF with no priced lines is retried with the model."""
    client = _FakeClient()
    pdf = _make_text_pdf(["Just some prose", "with no prices"])

    bill = await _parser(client).parse(pdf)

    assert len(client.calls) == 1
    assert len(bill.items) == 2


async def test_unsupported_file_rejected() -> None:
    """Anything that isn't a PDF or a supported image is refused."""
    with pytest.raises(UnsupportedContentTypeError):
        await _parser(_FakeClient()).parse(b"plain text, not a receipt")


async def test_corrupt_image_rejected() -> None:
    """A file with image magic bytes but no readable image is unrecognised."""
    with pytest.raises(UnrecognizedFormatError):
        await _parser(_FakeClient()).parse(b"\x89PNG\r\n\x1a\n-broken")


async def test_reply_without_items_rejected() -> None:
    """If the model finds nothing, the job fails instead of posting nothing."""
    with pytest.raises(UnrecognizedFormatError):
        await _parser(_FakeClient({"items": []})).parse(_image("PNG"))
