"""Business logic for statement/bill imports -- see the build plan's Phase 9."""

import hashlib
import mimetypes
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.settings import settings
from app.dal.category_query import CategoryQuery
from app.dal.import_job_query import ImportJobQuery
from app.dal.imported_transaction_query import ImportedTransactionQuery
from app.dal.spent_query import SpentQuery
from app.dal.user_query import UserQuery
from app.db.sql.models.category import Category
from app.db.sql.models.enums import (
    CategoryKind,
    ImportedTransactionStatus,
    ImportStatus,
)
from app.db.sql.models.import_job import ImportedTransaction, ImportJob
from app.db.sql.models.statement_source import StatementSourceRecord
from app.db.sql.models.users import User
from app.libs.openrouter.client import OpenRouterError
from app.libs.parsers.base import (
    ParsedBill,
    ParsedTransaction,
    UnparseableRow,
    UnrecognizedFormatError,
    UnsupportedContentTypeError,
)
from app.libs.parsers.registry import StatementParser
from app.services.account_service import AccountService
from app.services.imports.storage import ImportFileStore
from app.services.income_service import IncomeService
from app.services.spent_service import SpentNotFoundError, SpentService
from app.services.statement_source_service import (
    MARKET_BILL_CODE,
    StatementSourceService,
)

#: How far a candidate spent's amount may differ from a bill's parsed
#: total and still count as an auto-match -- covers rounding, not a
#: genuinely different purchase.
_BILL_MATCH_TOLERANCE = Decimal("0.01")

_FILE_EXPIRED_MESSAGE = "Uploaded file expired before it could be processed."


class ImportJobNotFoundError(Exception):
    """Raised when an import job isn't owned by the requesting user."""


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds ``imports_max_file_size_bytes``."""


class BillAccountRequiredError(Exception):
    """
    Raised creating a new spent from an unmatched bill without an account.

    A receipt carries no account of its own -- same reasoning as
    ``WishlistService.realise_item``'s create-a-new-spent path.
    """


def _dedupe_key_for(row: ParsedTransaction | UnparseableRow) -> str:
    """
    Compute a stable dedupe key for one parsed statement row.

    Used for *every* row, failed or not, so re-uploading an overlapping
    (or identical) export never double-records anything -- not just the
    successfully parsed rows.

    :param row: a parsed transaction, or a row the parser couldn't make
        sense of.
    :return: the provider's own transaction id when there is one,
        otherwise a hash of the row's identifying content.
    """
    if isinstance(row, UnparseableRow):
        return hashlib.sha256(row.raw_text.encode()).hexdigest()
    if row.dedupe_key:
        return row.dedupe_key
    raw = f"{row.occurred_at.isoformat()}|{row.amount}|{row.description}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _serialize_transaction(row: ParsedTransaction) -> dict[str, Any]:
    return {
        "dedupe_key": row.dedupe_key,
        "occurred_at": row.occurred_at.isoformat(),
        "amount": str(row.amount),
        "description": row.description,
        "counterparty": row.counterparty,
        "currency": row.currency,
    }


def _serialize_unparseable(row: UnparseableRow) -> dict[str, Any]:
    return {"raw_text": row.raw_text, "reason": row.reason}


class ImportService:
    """
    Business logic for uploading and processing statement/bill imports.

    Builds its own DAL query objects plus :class:`~app.services.
    account_service.AccountService`, :class:`~app.services.spent_service.
    SpentService`, and :class:`~app.services.income_service.IncomeService`
    from the db session it's given, reusing their creation logic for the
    spents/incomes/line-items an import produces rather than duplicating
    it -- callers never construct any of these themselves.
    """

    def __init__(self, session: AsyncSession, file_store: ImportFileStore) -> None:
        self.session = session
        self.file_store = file_store
        self.jobs = ImportJobQuery(session)
        self.imported_transactions = ImportedTransactionQuery(session)
        self.categories = CategoryQuery(session)
        self.spents = SpentQuery(session)
        self.users = UserQuery(session)
        self.account_service = AccountService(session)
        self.spent_service = SpentService(session)
        self.income_service = IncomeService(session)
        self.source_service = StatementSourceService(session)

    async def _fallback_category(self, kind: CategoryKind) -> Category:
        return cast(Category, await self.categories.get_builtin("Uncategorized", kind))

    async def start_statement_import(
        self, actor: User, account_id: uuid.UUID, file_bytes: bytes, filename: str
    ) -> ImportJob:
        """
        Start a bank/broker statement import, enqueuing its background parse.

        :param actor: user starting the import.
        :param account_id: which of ``actor``'s accounts this statement
            belongs to -- every transaction in the file posts here, and
            ``source`` is derived from this account, never supplied
            directly.
        :param file_bytes: the raw uploaded file.
        :param filename: the upload's original filename.
        :raises AccountNotOwnedError: if ``account_id`` isn't ``actor``'s.
        :raises AccountHasNoImportSourceError: if that account has no
            ``source`` configured (e.g. a manually-tracked cash wallet).
        :raises FileTooLargeError: if the file exceeds
            ``imports_max_file_size_bytes``.
        :return: the created job, ``status=PENDING`` -- the caller (the
            ``/imports/statements`` route) enqueues
            ``app.tasks.imports.process_statement_import`` against its
            id; not done here, since services never import from
            ``app.tasks`` (that's the one-directional dependency the
            whole codebase keeps, see ``app/services/__init__.py``).
        """
        if len(file_bytes) > settings.imports_max_file_size_bytes:
            raise FileTooLargeError
        account = await self.account_service.require_import_source(actor, account_id)
        job = await self.jobs.create(
            user_id=actor.id,
            source_id=account.source_id,
            account_id=account.id,
            original_filename=filename,
            status=ImportStatus.PENDING,
        )
        await self.file_store.save(job.id, file_bytes)
        await self.session.refresh(job)
        return job

    async def start_bill_import(
        self,
        actor: User,
        file_bytes: bytes,
        filename: str,
        *,
        target_spent_id: uuid.UUID | None = None,
        account_id: uuid.UUID | None = None,
    ) -> ImportJob:
        """
        Start a market-bill/receipt import, enqueuing its background parse.

        :param actor: user starting the import.
        :param file_bytes: the raw uploaded file.
        :param filename: the upload's original filename.
        :param target_spent_id: an existing spent (owned by ``actor``) to
            attach the bill's items to, if already known -- the common
            "attach a receipt" flow from a spent's own detail screen.
        :param account_id: which account to post a brand-new spent to,
            used only if no ``target_spent_id`` is given and no single
            existing spent obviously matches. Never stored on the job
            itself (``ImportJob.account_id`` stays ``NULL`` for a bill,
            per its own docstring) -- threaded straight through to the
            background task instead.
        :raises FileTooLargeError: if the file exceeds
            ``imports_max_file_size_bytes``.
        :raises BillAccountRequiredError: if neither ``target_spent_id``
            nor ``account_id`` is given -- rejected up front, since the
            parsed receipt has nowhere to go otherwise.
        :return: the created job, ``status=PENDING`` -- the caller (the
            ``/imports/bills`` route) enqueues
            ``app.tasks.imports.process_bill_import`` against its id,
            passing ``account_id`` straight through (see this method's
            own note on why it isn't enqueued here).
        """
        if len(file_bytes) > settings.imports_max_file_size_bytes:
            raise FileTooLargeError
        if target_spent_id is None and account_id is None:
            raise BillAccountRequiredError(
                "Send either target_spent_id or account_id with a bill upload."
            )
        bill_source = cast(
            StatementSourceRecord,
            await self.source_service.get_by_code(MARKET_BILL_CODE),
        )
        job = await self.jobs.create(
            user_id=actor.id,
            source_id=bill_source.id,
            account_id=None,
            original_filename=filename,
            status=ImportStatus.PENDING,
            target_spent_id=target_spent_id,
        )
        await self.file_store.save(job.id, file_bytes)
        await self.session.refresh(job)
        return job

    async def process_statement_import(self, job_id: uuid.UUID) -> None:
        """
        Parse a started statement import job and post its transactions.

        Every row keeps its own date and posts to the job's account;
        already-imported rows (by dedupe key, computed for every row so
        re-uploading is always safe) are skipped rather than re-posted or
        re-recorded -- a second ``ImportedTransaction`` sharing a dedupe
        key would violate that table's own uniqueness constraint anyway.

        :param job_id: the job to process (created by, and enqueued from,
            :meth:`start_statement_import`).
        """
        job = cast(ImportJob, await self.jobs.get(job_id))
        actor = cast(User, await self.users.get_by_id(job.user_id))
        file_bytes = await self.file_store.pop(job_id)
        if file_bytes is None:
            await self.jobs.update(
                job_id,
                status=ImportStatus.FAILED,
                error_message=_FILE_EXPIRED_MESSAGE,
            )
            return

        try:
            rows = await StatementParser(job.source).parse(file_bytes)
        except (
            UnrecognizedFormatError,
            UnsupportedContentTypeError,
            OpenRouterError,
            NotImplementedError,
        ) as exc:
            await self.jobs.update(
                job_id, status=ImportStatus.FAILED, error_message=str(exc)
            )
            return

        imported_count = 0
        duplicate_count = 0
        failed_count = 0
        expense_fallback: Category | None = None
        income_fallback: Category | None = None

        for row in rows:
            dedupe_key = _dedupe_key_for(row)
            if await self.imported_transactions.exists_by_dedupe_key(
                job.user_id, job.source_id, dedupe_key
            ):
                duplicate_count += 1
                continue

            if isinstance(row, UnparseableRow):
                await self.imported_transactions.create(
                    import_job_id=job_id,
                    user_id=job.user_id,
                    source_id=job.source_id,
                    dedupe_key=dedupe_key,
                    raw_payload=_serialize_unparseable(row),
                    status=ImportedTransactionStatus.FAILED,
                )
                failed_count += 1
                continue

            spent_id: uuid.UUID | None = None
            income_id: uuid.UUID | None = None
            if row.amount < 0:
                if expense_fallback is None:
                    expense_fallback = await self._fallback_category(
                        CategoryKind.EXPENSE
                    )
                spent = await self.spent_service.create(
                    actor,
                    account_id=cast(uuid.UUID, job.account_id),
                    category_id=cast(int, expense_fallback.id),
                    amount=-row.amount,
                    spent_at=row.occurred_at,
                    description=row.description or None,
                )
                spent_id = spent.id
            else:
                if income_fallback is None:
                    income_fallback = await self._fallback_category(CategoryKind.INCOME)
                income = await self.income_service.create(
                    actor,
                    account_id=cast(uuid.UUID, job.account_id),
                    category_id=cast(int, income_fallback.id),
                    amount=row.amount,
                    received_at=row.occurred_at,
                    description=row.description or None,
                )
                income_id = income.id

            await self.imported_transactions.create(
                import_job_id=job_id,
                user_id=job.user_id,
                source_id=job.source_id,
                dedupe_key=dedupe_key,
                spent_id=spent_id,
                income_id=income_id,
                raw_payload=_serialize_transaction(row),
                status=ImportedTransactionStatus.IMPORTED,
            )
            imported_count += 1

        await self.jobs.update(
            job_id,
            status=ImportStatus.COMPLETED,
            imported_count=imported_count,
            duplicate_count=duplicate_count,
            failed_count=failed_count,
        )

    async def _match_or_create_bill_target(
        self, actor: User, bill: ParsedBill, account_id: uuid.UUID | None
    ) -> uuid.UUID:
        total = bill.total_amount
        if total is None:
            total = sum((item.amount for item in bill.items), Decimal("0"))

        candidates = []
        if bill.purchased_at is not None:
            candidates = await self.spents.list_bill_match_candidates(
                actor.id, bill.purchased_at, total, tolerance=_BILL_MATCH_TOLERANCE
            )
        if len(candidates) == 1:
            return candidates[0].id

        if account_id is None:
            raise BillAccountRequiredError(
                "No single matching spent found -- an account_id is required "
                "to create a new one for this receipt."
            )
        category = await self.categories.get_builtin(
            "Groceries", CategoryKind.EXPENSE
        ) or await self._fallback_category(CategoryKind.EXPENSE)
        new_spent = await self.spent_service.create(
            actor,
            account_id=account_id,
            category_id=cast(int, category.id),
            amount=total,
            spent_at=bill.purchased_at or date.today(),
            description=bill.merchant,
        )
        return new_spent.id

    async def process_bill_import(
        self, job_id: uuid.UUID, account_id: uuid.UUID | None = None
    ) -> None:
        """
        Parse a started bill import job and attach its items to a spent.

        Either the caller's own ``target_spent_id``, a single obviously-
        matching existing spent, or (failing both) a newly created one --
        see the build plan's Phase 9 for the exact matching rule.

        :param job_id: the job to process (created by, and enqueued from,
            :meth:`start_bill_import`).
        :param account_id: passed straight through from
            :meth:`start_bill_import` -- only used if a new spent ends up
            getting created.
        """
        job = cast(ImportJob, await self.jobs.get(job_id))
        actor = cast(User, await self.users.get_by_id(job.user_id))
        file_bytes = await self.file_store.pop(job_id)
        if file_bytes is None:
            await self.jobs.update(
                job_id,
                status=ImportStatus.FAILED,
                error_message=_FILE_EXPIRED_MESSAGE,
            )
            return
        content_type = (
            mimetypes.guess_type(job.original_filename)[0] or "application/octet-stream"
        )

        try:
            bill = await StatementParser(job.source).parse(file_bytes, content_type)
        except (
            UnrecognizedFormatError,
            UnsupportedContentTypeError,
            OpenRouterError,
        ) as exc:
            await self.jobs.update(
                job_id, status=ImportStatus.FAILED, error_message=str(exc)
            )
            return

        if job.target_spent_id is not None:
            spent_id = job.target_spent_id
        else:
            try:
                spent_id = await self._match_or_create_bill_target(
                    actor, bill, account_id
                )
            except BillAccountRequiredError as exc:
                await self.jobs.update(
                    job_id, status=ImportStatus.FAILED, error_message=str(exc)
                )
                return

        try:
            for item in bill.items:
                await self.spent_service.add_item(
                    actor,
                    spent_id,
                    name=item.name,
                    amount=item.amount,
                    quantity=item.quantity,
                )
        except SpentNotFoundError:
            await self.jobs.update(
                job_id,
                status=ImportStatus.FAILED,
                error_message="Target spent not found.",
            )
            return

        await self.jobs.update(
            job_id,
            status=ImportStatus.COMPLETED,
            imported_count=len(bill.items),
            target_spent_id=spent_id,
        )

    async def list_for_user(self, actor: User) -> list[ImportJob]:
        """
        List a user's import jobs.

        :param actor: user requesting the list.
        :return: matching jobs.
        """
        return await self.jobs.list_for_user(actor.id)

    async def get_owned(self, actor: User, job_id: uuid.UUID) -> ImportJob:
        """
        Fetch an import job owned by ``actor``.

        :param actor: user requesting the job.
        :param job_id: job to fetch.
        :raises ImportJobNotFoundError: if it isn't owned by ``actor``.
        :return: the job.
        """
        job = await self.jobs.get(job_id)
        if job is None or job.user_id != actor.id:
            raise ImportJobNotFoundError
        return job

    async def list_transactions(
        self, actor: User, job_id: uuid.UUID
    ) -> list[ImportedTransaction]:
        """
        List the parsed rows belonging to an import job owned by ``actor``.

        :param actor: user requesting the list.
        :param job_id: parent job.
        :raises ImportJobNotFoundError: if the job isn't owned by ``actor``.
        :return: the job's parsed rows.
        """
        await self.get_owned(actor, job_id)
        return await self.imported_transactions.list_by_job(job_id)
