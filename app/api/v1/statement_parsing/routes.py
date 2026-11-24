import base64
import uuid
from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.statement_parsing import get_statement_parse_service
from app.api.v1.statement_parsing.schema import (
    ParseJobRead,
    PendingTransactionRead,
    PendingTransactionSave,
    SavedTransaction,
)
from app.config.settings import settings
from app.db.sql.models.statement_parse_job import StatementParseJob
from app.db.sql.models.users import User
from app.services.account_service import AccountNotOwnedError
from app.services.import_service import FileTooLargeError
from app.services.statement_parse_service import (
    InvalidCategoryError,
    ParseJobNotFoundError,
    PendingTransactionNotFoundError,
    StatementParseService,
    TooManyFilesError,
    UnsupportedFileError,
)
from app.tasks.statement_parsing import process_statement_parse

router = APIRouter(prefix="/statement-parsing", tags=["statement-parsing"])

_NOT_FOUND = "Pending transaction not found or expired."


@router.post(
    "/parse", response_model=ParseJobRead, status_code=status.HTTP_202_ACCEPTED
)
async def parse_statements(
    files: list[UploadFile] = File(...),
    account_id: uuid.UUID | None = Form(None),
    user: RequestUser = Depends(require_auth),
    service: StatementParseService = Depends(get_statement_parse_service),
) -> StatementParseJob:
    """
    Start parsing uploaded statement files in the background.

    The files are never stored. Poll ``GET /parse/{job_id}/status``; once it
    reports ``completed``, collect the rows from ``GET /transactions``. Each
    row stays cached for an hour until it is saved or declined, and is
    flagged with ``duplicate_of`` when it matches an existing record or
    another pending row. Nothing is written to the ledger here -- the client
    reviews each row, fills in the account and category, and saves it.

    :param files: PDFs, images (JPEG/PNG/WebP) or CSV/text exports; several
        files are treated as parts of one statement.
    :param account_id: the account the statement belongs to, if known.
    :param user: the authenticated user.
    :param service: statement parse service.
    :raises HTTPException: 400/404/413/415, see the body.
    :return: the created job, ``status=pending``.
    """
    uploads = [
        (f.filename or "upload", await f.read(settings.imports_max_file_size_bytes + 1))
        for f in files
    ]
    try:
        job = await service.start(cast(User, user.unwrap()), uploads, account_id)
    except TooManyFilesError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload between one and "
            f"{settings.statement_parsing_max_files} files.",
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File is too large.",
        ) from exc
    except UnsupportedFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, image (JPEG/PNG/WebP) and text files are supported.",
        ) from exc
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc
    # The worker reads the job row, so it must be committed before enqueuing.
    await service.session.commit()
    await process_statement_parse.kiq(
        job.id,
        [(name, base64.b64encode(data).decode()) for name, data in uploads],
    )
    return job


@router.get("/parse/{job_id}/status", response_model=ParseJobRead)
async def get_parse_status(
    job_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    service: StatementParseService = Depends(get_statement_parse_service),
) -> StatementParseJob:
    """
    Poll a parse job's status.

    :param job_id: job returned by ``POST /parse``.
    :param user: the authenticated user.
    :param service: statement parse service.
    :raises HTTPException: 404, if the job isn't the user's.
    :return: the job; ``failed`` carries an ``error_message``.
    """
    try:
        return await service.get_job(cast(User, user.unwrap()), job_id)
    except ParseJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Parse job not found."
        ) from exc


@router.get("/transactions", response_model=list[PendingTransactionRead])
async def list_pending_transactions(
    job_id: str | None = None,
    user: RequestUser = Depends(require_auth),
    service: StatementParseService = Depends(get_statement_parse_service),
) -> list[PendingTransactionRead]:
    """
    Collect the parsed transactions still awaiting a decision.

    Lets a client that lost its connection (or reloaded) pick the review up
    where it left off; rows disappear an hour after parsing, or as soon as
    they are saved or declined.

    :param job_id: only rows from this upload.
    :param user: the authenticated user.
    :param service: statement parse service.
    :return: pending transactions, most recent date first.
    """
    pending = await service.list_pending(cast(User, user.unwrap()))
    return [
        PendingTransactionRead(**tx)
        for tx in pending
        if job_id is None or tx["job_id"] == job_id
    ]


@router.post("/transactions/{tx_id}/save", response_model=SavedTransaction)
async def save_pending_transaction(
    tx_id: str,
    payload: PendingTransactionSave,
    user: RequestUser = Depends(require_auth),
    service: StatementParseService = Depends(get_statement_parse_service),
) -> SavedTransaction:
    """
    Save a pending transaction as a spent or income and drop it from the cache.

    :param tx_id: pending transaction id.
    :param payload: account, category, and any corrections.
    :param user: the authenticated user.
    :param service: statement parse service.
    :raises HTTPException: 404, if it isn't pending or the account isn't the
        user's; 400, if the category can't be used for it.
    :return: the created record.
    """
    try:
        kind, record_id = await service.save(
            cast(User, user.unwrap()),
            tx_id,
            account_id=payload.account_id,
            category_id=payload.category_id,
            amount=payload.amount,
            occurred_at=payload.occurred_at,
            description=payload.description,
            visibility=payload.visibility,
        )
    except PendingTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
        ) from exc
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc
    except InvalidCategoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category doesn't exist or doesn't fit this transaction.",
        ) from exc
    return SavedTransaction(kind=kind, id=record_id)


@router.delete("/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
async def decline_pending_transaction(
    tx_id: str,
    user: RequestUser = Depends(require_auth),
    service: StatementParseService = Depends(get_statement_parse_service),
) -> None:
    """
    Decline a pending transaction, dropping it from the cache.

    Also what a client calls after saving a row through the regular
    spent/income endpoints instead of ``/save``.

    :param tx_id: pending transaction id.
    :param user: the authenticated user.
    :param service: statement parse service.
    :raises HTTPException: 404, if it isn't pending.
    """
    try:
        await service.decline(cast(User, user.unwrap()), tx_id)
    except PendingTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
        ) from exc
