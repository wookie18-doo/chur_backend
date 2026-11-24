import base64
import json
import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.settings import settings
from app.dal.account_query import AccountQuery
from app.dal.category_query import CategoryQuery
from app.dal.income_query import IncomeQuery
from app.dal.spent_query import SpentQuery
from app.dal.statement_parse_job_query import StatementParseJobQuery
from app.dal.user_query import UserQuery
from app.db.sql.models.enums import CategoryKind, ImportStatus, Visibility
from app.db.sql.models.income import Income
from app.db.sql.models.spent import Spent
from app.db.sql.models.statement_parse_job import StatementParseJob
from app.db.sql.models.users import User
from app.libs.openrouter.client import (
    OpenRouterClient,
    OpenRouterError,
    OpenRouterNotConfiguredError,
)
from app.services.account_service import AccountNotOwnedError
from app.services.import_service import FileTooLargeError
from app.services.income_service import IncomeService
from app.services.pending_transaction_cache import PendingTransactionCache
from app.services.spent_service import SpentService

Kind = Literal["expense", "income"]

_SYSTEM_PROMPT = """\
You extract bank-account transactions from bank statements, card-app \
screenshots and exports in any language or layout. Reply with a single JSON \
object and nothing else:
{"transactions": [{"date": "YYYY-MM-DD", "amount": "12.34", \
"direction": "expense" | "income", "currency": "EUR", \
"description": "...", "counterparty": "..." | null, \
"category_id": <integer from the list> | null}]}

Rules:
- One entry per booked transaction, in the order shown. Never invent rows.
- Skip balances, totals, summaries, fees summaries, and reserved/pending \
holds that are not yet booked.
- "amount" is always positive, with a dot as the decimal separator and no \
thousands separators. Money leaving the account (debit, payment, withdrawal, \
negative amount) is "expense"; money arriving (credit, deposit, refund, \
positive amount) is "income".
- If a row shows no year, infer it from the statement period or the other \
dates. If a row shows both a booking and a value date, use the booking date.
- "currency" is the ISO 4217 code of the transaction's own amount.
- "description" is the merchant or payment reference as printed, short and \
without the amount. "counterparty" is the other party's name when it is \
distinct from the description, else null.
- "category_id" must be one of the ids in the provided list that fits the \
transaction and its direction, or null when none clearly fits.
- If the files hold no transactions, return {"transactions": []}.
"""

_MAX_DESCRIPTION = 500


class UnsupportedFileError(Exception):
    """Raised when an uploaded file is neither a PDF, an image, nor text."""


class TooManyFilesError(Exception):
    """Raised when an upload carries more than the allowed number of files."""


class StatementParseError(Exception):
    """Raised when the model's reply can't be turned into transactions."""


class ParseJobNotFoundError(Exception):
    """Raised when a parse job doesn't exist or isn't the user's."""


class PendingTransactionNotFoundError(Exception):
    """Raised when a pending transaction is unknown, expired, or not yours."""


class InvalidCategoryError(Exception):
    """Raised when a category is unusable for the transaction being saved."""


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
        raise UnsupportedFileError(filename)
    if mime == "application/pdf":
        return {
            "type": "file",
            "file": {"filename": filename, "file_data": _data_url(mime, data)},
        }
    if mime.startswith("image/"):
        return {"type": "image_url", "image_url": {"url": _data_url(mime, data)}}
    return {
        "type": "text",
        "text": f"File {filename}:\n{data.decode('utf-8')}",
    }


def _extract_json(raw: str) -> Any:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise StatementParseError("The model did not return valid JSON.") from exc


def _normalise_row(
    row: Any, categories: dict[int, CategoryKind]
) -> dict[str, Any] | None:
    """Validate one model-produced row; ``None`` means it is unusable."""
    if not isinstance(row, dict):
        return None
    try:
        occurred_at = date.fromisoformat(str(row["date"]).strip())
        amount = abs(Decimal(str(row["amount"]).strip().replace(",", ""))).quantize(
            Decimal("0.01")
        )
    except (KeyError, ValueError, InvalidOperation):
        return None
    direction = str(row.get("direction", "")).strip().lower()
    if direction not in ("expense", "income") or amount <= 0:
        return None

    description = str(row.get("description") or "").strip()[:_MAX_DESCRIPTION]
    counterparty = row.get("counterparty")
    category_id = row.get("category_id")
    wanted = CategoryKind.EXPENSE if direction == "expense" else CategoryKind.INCOME
    if not isinstance(category_id, int) or categories.get(category_id) != wanted:
        category_id = None
    currency = str(row.get("currency") or "").strip().upper()
    return {
        "occurred_at": occurred_at.isoformat(),
        "amount": str(amount),
        "kind": direction,
        "currency": currency if len(currency) == 3 else None,
        "description": description,
        "counterparty": (str(counterparty).strip() or None) if counterparty else None,
        "suggested_category_id": category_id,
    }


def _mark_duplicates(
    rows: list[dict[str, Any]],
    existing: list[tuple[str, str, str, str, str]],
    source: Literal["existing", "pending"],
) -> None:
    """
    Flag rows that match an already-known transaction.

    ``existing`` holds ``(date, amount, kind, record_kind, record_id)``.
    Matching is one-to-one: a statement with two identical rows against one
    stored record only flags the first, so genuine repeat purchases aren't
    both swallowed.

    :param rows: normalised rows, updated in place.
    :param existing: known transactions to match against.
    :param source: where ``existing`` came from, reported to the client.
    """
    pool: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
    for occurred_at, amount, kind, record_kind, record_id in existing:
        pool[(occurred_at, amount, kind)].append((record_kind, record_id))
    for row in rows:
        if row["duplicate_of"] is not None:
            continue
        matches = pool.get((row["occurred_at"], row["amount"], row["kind"]))
        if matches:
            record_kind, record_id = matches.pop(0)
            row["duplicate_of"] = {
                "source": source,
                "kind": record_kind,
                "id": record_id,
            }


class StatementParseService:
    """
    Parses uploaded statements with an LLM in the background.

    Uploaded files are never stored: they travel to the background task and
    live in memory only while it runs.
    Parsed rows are parked in :class:`PendingTransactionCache` until the
    client saves (:meth:`save`) or declines (:meth:`decline`) each one, or
    the cache's TTL lapses.
    """

    def __init__(
        self,
        session: AsyncSession,
        cache: PendingTransactionCache,
        llm: OpenRouterClient,
    ) -> None:
        self.session = session
        self.cache = cache
        self.llm = llm
        self.accounts = AccountQuery(session)
        self.jobs = StatementParseJobQuery(session)
        self.users = UserQuery(session)
        self.categories = CategoryQuery(session)
        self.spents = SpentQuery(session)
        self.incomes = IncomeQuery(session)
        self.spent_service = SpentService(session)
        self.income_service = IncomeService(session)

    async def start(
        self,
        actor: User,
        files: list[tuple[str, bytes]],
        account_id: uuid.UUID | None = None,
    ) -> StatementParseJob:
        """
        Validate an upload and create the job that will parse it.

        Everything the client can fix is checked here, so it hears about it
        immediately instead of through a failed job. The caller hands the
        files to the background task (:meth:`process`) -- they are never
        stored.

        :param actor: user uploading.
        :param files: ``(filename, content)`` pairs; PDFs, images or text.
        :param account_id: the account the statement belongs to, if known.
        :raises TooManyFilesError: if there are too many files.
        :raises FileTooLargeError: if any file exceeds the size limit.
        :raises UnsupportedFileError: if a file isn't a supported type.
        :raises AccountNotOwnedError: if ``account_id`` isn't ``actor``'s.
        :return: the created job, ``status=pending``.
        """
        if not files or len(files) > settings.statement_parsing_max_files:
            raise TooManyFilesError
        if any(len(data) > settings.imports_max_file_size_bytes for _, data in files):
            raise FileTooLargeError
        for name, data in files:
            if _sniff(data) is None:
                raise UnsupportedFileError(name)
        if account_id is not None:
            account = await self.accounts.get(account_id)
            if account is None or account.user_id != actor.id:
                raise AccountNotOwnedError
        return await self.jobs.create(
            user_id=actor.id,
            account_id=account_id,
            filenames=[name for name, _ in files],
            status=ImportStatus.PENDING,
        )

    async def get_job(self, actor: User, job_id: uuid.UUID) -> StatementParseJob:
        """
        Fetch a parse job owned by ``actor``.

        :param actor: user asking.
        :param job_id: job to fetch.
        :raises ParseJobNotFoundError: if it isn't ``actor``'s.
        :return: the job.
        """
        job = await self.jobs.get(job_id)
        if job is None or job.user_id != actor.id:
            raise ParseJobNotFoundError
        return job

    async def process(self, job_id: uuid.UUID, files: list[tuple[str, bytes]]) -> None:
        """
        Run a started job: parse the files and park the rows in the cache.

        Never raises for expected failures -- they end the job as ``failed``
        with a client-safe message, which is what the client polls for.

        :param job_id: job created by :meth:`start`.
        :param files: the uploaded ``(filename, content)`` pairs.
        """
        job = await self.jobs.get(job_id)
        if job is None:
            return
        await self.jobs.update(job_id, status=ImportStatus.PROCESSING)
        # Commit now so a polling client sees "processing" while the (slow)
        # model call runs, not only the final state.
        await self.session.commit()
        try:
            rows, skipped = await self._parse_files(job, files)
        except OpenRouterNotConfiguredError:
            await self._fail(job_id, "Statement parsing is not configured.")
        except (OpenRouterError, StatementParseError):
            await self._fail(job_id, "Could not parse the statement.")
        except Exception:
            logger.exception("Statement parse job {} crashed", job_id)
            await self.session.rollback()
            await self._fail(job_id, "Unexpected error while parsing.")
        else:
            await self.jobs.update(
                job_id,
                status=ImportStatus.COMPLETED,
                transaction_count=len(rows),
                duplicate_count=sum(r["duplicate_of"] is not None for r in rows),
                skipped_count=skipped,
            )

    async def _fail(self, job_id: uuid.UUID, message: str) -> None:
        await self.jobs.update(
            job_id, status=ImportStatus.FAILED, error_message=message
        )

    async def _parse_files(
        self, job: StatementParseJob, files: list[tuple[str, bytes]]
    ) -> tuple[list[dict[str, Any]], int]:
        actor = cast(User, await self.users.get_by_id(job.user_id))
        parts = [_file_part(name, data) for name, data in files]

        categories = [
            *await self.categories.list_visible(actor.id, CategoryKind.EXPENSE),
            *await self.categories.list_visible(actor.id, CategoryKind.INCOME),
        ]
        kinds = {int(c.id): c.kind for c in categories if c.id is not None}
        category_list = "\n".join(
            f"{c.id}: {c.name} ({c.kind.value})" for c in categories
        )
        instruction = (
            f"Today is {date.today().isoformat()}. Extract the transactions "
            "from the attached statement file(s); multiple files are parts of "
            f"the same statement.\n\nCategories:\n{category_list}"
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [{"type": "text", "text": instruction}, *parts],
            },
        ]
        plugins = None
        if settings.openrouter_pdf_engine:
            plugins = [
                {"id": "file-parser", "pdf": {"engine": settings.openrouter_pdf_engine}}
            ]
        reply = await self.llm.complete_json(messages, plugins=plugins)

        payload = _extract_json(reply)
        raw_rows = payload.get("transactions") if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            raise StatementParseError("The model reply has no transaction list.")

        rows = [
            normalised
            for raw in raw_rows
            if (normalised := _normalise_row(raw, kinds)) is not None
        ]
        created_at = datetime.now(UTC).isoformat()
        for row in rows:
            row.update(
                id=uuid.uuid4().hex,
                job_id=str(job.id),
                filenames=job.filenames,
                account_id=str(job.account_id) if job.account_id else None,
                duplicate_of=None,
                created_at=created_at,
            )
        await self._flag_duplicates(actor, rows, job.account_id)
        await self.cache.add_many(actor.id, rows)
        return rows, len(raw_rows) - len(rows)

    async def _flag_duplicates(
        self, actor: User, rows: list[dict[str, Any]], account_id: uuid.UUID | None
    ) -> None:
        if not rows:
            return
        dates = [date.fromisoformat(r["occurred_at"]) for r in rows]
        spents = await self.spents.list_for_dedupe(
            actor.id, min(dates), max(dates), account_id
        )
        incomes = await self.incomes.list_for_dedupe(
            actor.id, min(dates), max(dates), account_id
        )
        existing = [
            (s.spent_at.isoformat(), str(s.amount), "expense", "spent", str(s.id))
            for s in spents
        ] + [
            (i.received_at.isoformat(), str(i.amount), "income", "income", str(i.id))
            for i in incomes
        ]
        _mark_duplicates(rows, existing, "existing")

        pending = [
            (p["occurred_at"], p["amount"], p["kind"], "pending", p["id"])
            for p in await self.cache.list(actor.id)
            if account_id is None or p.get("account_id") in (None, str(account_id))
        ]
        _mark_duplicates(rows, pending, "pending")

    async def list_pending(self, actor: User) -> list[dict[str, Any]]:
        """
        List the user's parsed transactions still awaiting a decision.

        :param actor: user asking.
        :return: pending transactions, ordered by date then upload order.
        """
        pending = await self.cache.list(actor.id)
        return sorted(pending, key=lambda p: p["occurred_at"], reverse=True)

    async def decline(self, actor: User, tx_id: str) -> None:
        """
        Discard a pending transaction.

        :param actor: user declining.
        :param tx_id: pending transaction id.
        :raises PendingTransactionNotFoundError: if it isn't pending.
        """
        if not await self.cache.remove(actor.id, tx_id):
            raise PendingTransactionNotFoundError

    async def save(
        self,
        actor: User,
        tx_id: str,
        *,
        account_id: uuid.UUID,
        category_id: int,
        amount: Decimal | None = None,
        occurred_at: date | None = None,
        description: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
    ) -> tuple[Literal["spent", "income"], uuid.UUID]:
        """
        Turn a pending transaction into a real spent or income.

        :param actor: user saving.
        :param tx_id: pending transaction id.
        :param account_id: account to post to -- must be ``actor``'s.
        :param category_id: category to file under -- built-in or
            ``actor``'s own, of the matching expense/income kind.
        :param amount: corrected amount, if the parse was off.
        :param occurred_at: corrected date, if the parse was off.
        :param description: corrected description, if the parse was off.
        :param visibility: who besides ``actor`` may see it.
        :raises PendingTransactionNotFoundError: if it isn't pending.
        :raises AccountNotOwnedError: if ``account_id`` isn't ``actor``'s.
        :raises InvalidCategoryError: if the category isn't usable.
        :return: what was created and its id; the transaction is dropped
            from the cache only after that succeeds.
        """
        tx = await self.cache.get(actor.id, tx_id)
        if tx is None:
            raise PendingTransactionNotFoundError
        account = await self.accounts.get(account_id)
        if account is None or account.user_id != actor.id:
            raise AccountNotOwnedError
        category = await self.categories.get(category_id)
        wanted = (
            CategoryKind.EXPENSE if tx["kind"] == "expense" else CategoryKind.INCOME
        )
        if (
            category is None
            or category.kind != wanted
            or category.owner_id not in (None, actor.id)
        ):
            raise InvalidCategoryError

        final_amount = amount if amount is not None else Decimal(tx["amount"])
        final_date = occurred_at or date.fromisoformat(tx["occurred_at"])
        final_description = (
            description if description is not None else tx["description"]
        ) or None
        record: Spent | Income
        record_kind: Literal["spent", "income"]
        if tx["kind"] == "expense":
            record = await self.spent_service.create(
                actor,
                account_id=account_id,
                category_id=category_id,
                amount=final_amount,
                spent_at=final_date,
                description=final_description,
                visibility=visibility,
            )
            record_kind = "spent"
        else:
            record = await self.income_service.create(
                actor,
                account_id=account_id,
                category_id=category_id,
                amount=final_amount,
                received_at=final_date,
                description=final_description,
                visibility=visibility,
            )
            record_kind = "income"
        await self.cache.remove(actor.id, tx_id)
        return record_kind, record.id


__all__ = [
    "InvalidCategoryError",
    "OpenRouterError",
    "ParseJobNotFoundError",
    "PendingTransactionNotFoundError",
    "StatementParseError",
    "StatementParseService",
    "TooManyFilesError",
    "UnsupportedFileError",
]
