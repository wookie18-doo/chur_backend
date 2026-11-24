"""
Parser for statements from a provider with no dedicated parser.

Sends the file to OpenRouter's LLM and asks for the rows in a fixed JSON
shape, then wraps them in the same pydantic models the dedicated parsers use.
"""

import base64
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.config.settings import settings
from app.libs.openrouter.client import OpenRouterClient
from app.libs.parsers.base import (
    BaseParser,
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
    UnsupportedContentTypeError,
)

_SYSTEM_PROMPT = """\
You extract bank-account transactions from bank statements, card-app \
screenshots and exports in any language or layout. Reply with a single JSON \
object and nothing else:
{"transactions": [{"id": "<provider transaction id>" | null, \
"date": "YYYY-MM-DD", "amount": "-12.34", "currency": "EUR", \
"description": "...", "counterparty": "..." | null}], \
"unparseable": [{"raw_text": "<the row as printed>", "reason": "<why>"}]}

Rules:
- One entry per booked transaction, in the order shown. Never invent rows.
- Skip balances, totals, summaries and reserved/pending holds.
- "amount" is signed, with a dot as the decimal separator and no thousands \
separators: negative for money leaving the account, positive for money \
arriving.
- If a row shows no year, infer it from the statement period or the other \
dates. If a row shows both a booking and a value date, use the booking date.
- "currency" is the ISO 4217 code of the transaction's own amount.
- "description" is the merchant or payment reference as printed, short and \
without the amount. "counterparty" is the other party's name when it is \
distinct from the description, else null.
- "id" is the provider's own transaction id when the file shows one, else null.
- A row that is clearly a transaction but can't be read reliably goes to \
"unparseable" with its raw text instead of being guessed.
- If the file holds no transactions, return {"transactions": [], \
"unparseable": []}.
"""


class UnknownParser(BaseParser):
    """Parses a statement of any layout by asking an LLM through OpenRouter."""

    def __init__(self, client: OpenRouterClient | None = None) -> None:
        self.client = client or OpenRouterClient()

    async def parse(  # type: ignore[override]
        self, file_bytes: bytes, filename: str = "statement"
    ) -> list[ParsedTransaction | UnparseableRow]:
        """
        Parse a statement export of unknown provider.

        :param file_bytes: the raw uploaded file (PDF, image or text).
        :param filename: the upload's name, passed to the model as context.
        :raises UnsupportedContentTypeError: if the file is neither a PDF, an
            image nor text.
        :raises UnrecognizedFormatError: if the model's reply isn't the
            requested JSON shape.
        :raises OpenRouterError: if OpenRouter is unreachable, unconfigured or
            returns an unusable reply.
        :return: parsed transactions mixed with any rows that couldn't be.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Today is {date.today().isoformat()}. Extract the "
                            "transactions from the attached statement."
                        ),
                    },
                    _file_part(filename, file_bytes),
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


def _is_text(data: bytes) -> bool:
    if b"\x00" in data[:4096]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _sniff(data: bytes) -> str | None:
    magic = {
        b"%PDF": "application/pdf",
        b"\xff\xd8\xff": "image/jpeg",
        b"\x89PNG\r\n\x1a\n": "image/png",
    }
    for prefix, mime in magic.items():
        if data.startswith(prefix):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "text/plain" if _is_text(data) else None


def _data_url(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _file_part(filename: str, data: bytes) -> dict[str, Any]:
    mime = _sniff(data)
    if mime is None:
        raise UnsupportedContentTypeError(filename)
    if mime == "application/pdf":
        return {
            "type": "file",
            "file": {"filename": filename, "file_data": _data_url(mime, data)},
        }
    if mime.startswith("image/"):
        return {"type": "image_url", "image_url": {"url": _data_url(mime, data)}}
    return {"type": "text", "text": f"File {filename}:\n{data.decode('utf-8')}"}


def _extract_json(raw: str) -> Any:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise UnrecognizedFormatError("The model did not return valid JSON.") from exc


def _wrap_reply(payload: Any) -> list[ParsedTransaction | UnparseableRow]:
    if not isinstance(payload, dict) or not isinstance(
        payload.get("transactions"), list
    ):
        raise UnrecognizedFormatError("The model reply has no transaction list.")
    result: list[ParsedTransaction | UnparseableRow] = []
    for raw in payload["transactions"]:
        result.append(_to_transaction(raw))
    unparseable = payload.get("unparseable")
    for raw in unparseable if isinstance(unparseable, list) else []:
        if isinstance(raw, dict):
            result.append(
                UnparseableRow(
                    raw_text=str(raw.get("raw_text") or ""),
                    reason=str(raw.get("reason") or "Reported by the model."),
                )
            )
    return result


def _to_transaction(raw: Any) -> ParsedTransaction | UnparseableRow:
    if not isinstance(raw, dict):
        return UnparseableRow(raw_text=str(raw), reason="Not a transaction object.")
    try:
        occurred_at = date.fromisoformat(str(raw["date"]).strip())
        amount = Decimal(str(raw["amount"]).strip().replace(",", ""))
    except (KeyError, ValueError, InvalidOperation):
        return UnparseableRow(
            raw_text=json.dumps(raw, default=str), reason="Invalid date or amount."
        )
    currency = str(raw.get("currency") or "").strip().upper()
    if len(currency) != 3:
        return UnparseableRow(
            raw_text=json.dumps(raw, default=str), reason="Invalid currency."
        )
    counterparty = raw.get("counterparty")
    external_id = raw.get("id")
    return ParsedTransaction(
        dedupe_key=str(external_id).strip() or None if external_id else None,
        occurred_at=occurred_at,
        amount=amount,
        description=str(raw.get("description") or "").strip(),
        counterparty=str(counterparty).strip() or None if counterparty else None,
        currency=currency,
    )
