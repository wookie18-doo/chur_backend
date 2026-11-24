"""
Receipt parser: text-layer PDFs by heuristic, photos and scans by an LLM.

A digitally-generated (text-layer) PDF is read with a cheap line-based
heuristic tuned against no specific market's real layout yet -- **pin it
against actual receipts from the markets you actually use** (add them as
fixtures under ``tests/fixtures/imports/``) before relying on it; receipt
layouts vary enormously between stores.

Everything else -- PNG/JPEG/WebP/HEIC photos, image-only PDFs, and text PDFs
the heuristic can't make sense of -- is sent to a vision model through
OpenRouter, which reads the receipt in any layout or language.
"""

import asyncio
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pdfplumber
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.config.settings import settings
from app.libs.openrouter.client import OpenRouterClient
from app.libs.parsers.base import (
    BaseParser,
    ParsedBill,
    ParsedBillItem,
    UnrecognizedFormatError,
    UnsupportedContentTypeError,
)
from app.libs.parsers.unknown import _data_url, _extract_json

register_heif_opener()

#: Longest image side sent to the model; keeps phone photos affordable
#: while receipt text stays legible.
_MAX_IMAGE_SIDE = 2400
_JPEG_QUALITY = 88
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1")
_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/heic")

_SYSTEM_PROMPT = """\
You extract the purchased items from a photographed or scanned shop receipt \
in any language or layout. Reply with a single JSON object and nothing else:
{"merchant": "<shop name>" | null, "date": "YYYY-MM-DD" | null, \
"total": "12.34" | null, "items": [{"name": "...", "amount": "2.38", \
"quantity": "x2" | null}]}

Rules:
- One entry per purchased product, in the order printed. Never invent items.
- "amount" is that line's total price: positive, dot as decimal separator, \
no thousands separators or currency symbols.
- "quantity" is the printed quantity or weight as display text ("x2", \
"1.2 kg"), else null.
- Skip subtotals, tax lines, payment lines, change, loyalty points and \
discounts. "total" is the grand total paid.
- If a date shows no year, infer it from the rest of the receipt.
- If the image is not a receipt or nothing is legible, return {"items": []}.
"""

#: A line item: some name text, then a trailing price at the end of the
#: line (optionally preceded by a currency symbol), e.g.
#: "Milk 1 L                                    2.38" or "Bananas €1.99".
_ITEM_LINE = re.compile(r"^(?P<name>.+?)\s+[€$]?(?P<price>\d+[.,]\d{2})\s*$")
_TOTAL_LINE = re.compile(
    r"^\s*total\b.*?[€$]?\s*(?P<amount>\d+[.,]\d{2})\s*$", re.IGNORECASE
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMERIC_DATE = re.compile(r"\b(\d{2})[./](\d{2})[./](\d{4})\b")
#: e.g. "26 Sep 2026" -- a common receipt date style ISO/numeric patterns
#: alone would miss entirely.
_TEXT_MONTH_DATE = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_ABBREVIATIONS = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)

#: Lines that look item-shaped but never are -- excluded so they don't
#: get parsed as a €0.00 or nonsensical "product".
_SKIP_PREFIXES = ("subtotal", "tax", "vat", "change", "cash", "card", "total")


def _to_decimal(raw: str) -> Decimal:
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation as exc:
        raise UnrecognizedFormatError(f"Unparseable amount: {raw!r}") from exc


def _find_date(text: str) -> date | None:
    iso_match = _ISO_DATE.search(text)
    if iso_match:
        try:
            year, month, day = (int(part) for part in iso_match.groups())
            return date(year, month, day)
        except ValueError:
            pass

    text_month_match = _TEXT_MONTH_DATE.search(text)
    if text_month_match:
        day_str, month_name, year_str = text_month_match.groups()
        try:
            month = _MONTH_ABBREVIATIONS.index(month_name.lower()[:3]) + 1
            return date(int(year_str), month, int(day_str))
        except ValueError:
            pass

    numeric_match = _NUMERIC_DATE.search(text)
    if numeric_match:
        day_str, month_str, year_str = numeric_match.groups()
        try:
            return date(int(year_str), int(month_str), int(day_str))
        except ValueError:
            pass

    return None


class MarketBillParser(BaseParser):
    """Parses a receipt (text PDF, scanned PDF or photo) into its line items."""

    def __init__(self, client: OpenRouterClient | None = None) -> None:
        self.client = client or OpenRouterClient()

    async def parse(  # type: ignore[override]
        self, file_bytes: bytes, content_type: str | None = None
    ) -> ParsedBill:
        """
        Parse a receipt.

        The file's real type is sniffed from its bytes; ``content_type``
        (guessed from the filename) is not trusted, since phones often
        name a HEIC photo ``.jpg``.

        :param file_bytes: the raw uploaded file.
        :param content_type: the upload's declared MIME type, unused.
        :raises UnsupportedContentTypeError: if the file isn't a PDF or a
            PNG/JPEG/WebP/HEIC image.
        :raises UnrecognizedFormatError: if the file is unreadable or no
            receipt items could be found in it.
        :raises OpenRouterError: if the model call fails.
        :return: the parsed bill.
        """
        kind = _sniff(file_bytes)
        if kind == "application/pdf":
            text = await asyncio.to_thread(_pdf_text, file_bytes)
            if text.strip():
                try:
                    return _parse_text(text)
                except UnrecognizedFormatError:
                    pass
            part = {
                "type": "file",
                "file": {
                    "filename": "receipt.pdf",
                    "file_data": _data_url(kind, file_bytes),
                },
            }
        elif kind in _IMAGE_TYPES:
            jpeg = await asyncio.to_thread(_normalise_image, file_bytes)
            part = {
                "type": "image_url",
                "image_url": {"url": _data_url("image/jpeg", jpeg)},
            }
        else:
            raise UnsupportedContentTypeError(
                "Only PDF, PNG, JPEG, WebP and HEIC receipts are supported."
            )
        return await self._parse_with_llm(part)

    async def _parse_with_llm(self, part: dict[str, Any]) -> ParsedBill:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Today is {date.today().isoformat()}. Extract the "
                            "items from the attached receipt."
                        ),
                    },
                    part,
                ],
            },
        ]
        plugins = None
        if settings.openrouter_pdf_engine:
            plugins = [
                {"id": "file-parser", "pdf": {"engine": settings.openrouter_pdf_engine}}
            ]
        reply = await self.client.complete_json(messages, plugins=plugins)
        return _wrap_reply(_extract_json(reply))


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic"
    return None


def _pdf_text(file_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise UnrecognizedFormatError("Not a readable PDF file.") from exc


def _normalise_image(file_bytes: bytes) -> bytes:
    """Upright, shrink and re-encode any supported photo as JPEG."""
    try:
        with Image.open(io.BytesIO(file_bytes)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE))
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "JPEG", quality=_JPEG_QUALITY)
    except (UnidentifiedImageError, OSError) as exc:
        raise UnrecognizedFormatError("Not a readable image file.") from exc
    return buffer.getvalue()


def _wrap_reply(payload: Any) -> ParsedBill:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise UnrecognizedFormatError("The model reply has no item list.")
    items: list[ParsedBillItem] = []
    for raw in payload["items"]:
        item = _to_item(raw)
        if item is not None:
            items.append(item)
    if not items:
        raise UnrecognizedFormatError("No receipt items could be read from the file.")
    return ParsedBill(
        merchant=_clean(payload.get("merchant")),
        purchased_at=_to_date(payload.get("date")),
        total_amount=_to_amount(payload.get("total")),
        items=items,
    )


def _to_item(raw: Any) -> ParsedBillItem | None:
    if not isinstance(raw, dict):
        return None
    amount = _to_amount(raw.get("amount"))
    name = _clean(raw.get("name"))
    if amount is None or amount <= 0 or name is None:
        return None
    return ParsedBillItem(
        name=name, amount=amount, quantity=_clean(raw.get("quantity"))
    )


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _to_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        return None


def _to_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _parse_text(text: str) -> ParsedBill:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    merchant = lines[0] if lines else None
    purchased_at = _find_date(text)

    items: list[ParsedBillItem] = []
    total_amount: Decimal | None = None
    for line in lines:
        total_match = _TOTAL_LINE.match(line)
        if total_match:
            total_amount = _to_decimal(total_match.group("amount"))
            continue
        if line.lower().startswith(_SKIP_PREFIXES):
            continue
        item_match = _ITEM_LINE.match(line)
        if not item_match:
            continue
        items.append(
            ParsedBillItem(
                name=item_match.group("name").strip(),
                amount=_to_decimal(item_match.group("price")),
                quantity=None,
            )
        )

    if not items:
        raise UnrecognizedFormatError(
            "No priced lines found -- doesn't look like a receipt this "
            "heuristic recognizes."
        )

    return ParsedBill(
        merchant=merchant,
        purchased_at=purchased_at,
        total_amount=total_amount,
        items=items,
    )
