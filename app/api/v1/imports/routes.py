import uuid
from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.imports import get_import_service
from app.api.v1.imports.schema import ImportedTransactionRead, ImportJobRead
from app.config.settings import settings
from app.db.sql.models.import_job import ImportedTransaction, ImportJob
from app.db.sql.models.users import User
from app.services.account_service import (
    AccountHasNoImportSourceError,
    AccountNotOwnedError,
)
from app.services.import_service import (
    BillAccountRequiredError,
    FileTooLargeError,
    ImportJobNotFoundError,
    ImportService,
)
from app.tasks.imports import process_bill_import, process_statement_import

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "/statements", response_model=ImportJobRead, status_code=status.HTTP_202_ACCEPTED
)
async def import_statement(
    account_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    user: RequestUser = Depends(require_auth),
    import_service: ImportService = Depends(get_import_service),
) -> ImportJob:
    """
    Upload a bank/broker statement export for the given account.

    :param account_id: which of the user's accounts this statement
        belongs to -- ``source`` is derived from it, never chosen here.
    :param file: the statement export file.
    :param user: the authenticated user.
    :param import_service: import service.
    :raises HTTPException: 404, if the account isn't the user's; 400, if
        it has no import source configured; 413, if the file is too large.
    :return: the created job, ``status=pending``.
    """
    content = await file.read(settings.imports_max_file_size_bytes + 1)
    try:
        job = await import_service.start_statement_import(
            cast(User, user.unwrap()), account_id, content, file.filename or "upload"
        )
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc
    except AccountHasNoImportSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account has no import source configured.",
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File is too large.",
        ) from exc
    await process_statement_import.kiq(job.id)
    return job


@router.post(
    "/bills", response_model=ImportJobRead, status_code=status.HTTP_202_ACCEPTED
)
async def import_bill(
    file: UploadFile = File(...),
    target_spent_id: uuid.UUID | None = Form(None),
    account_id: uuid.UUID | None = Form(None),
    user: RequestUser = Depends(require_auth),
    import_service: ImportService = Depends(get_import_service),
) -> ImportJob:
    """
    Upload a market bill/receipt.

    :param file: the receipt file (text-layer PDF -- see
        ``MarketBillParser`` for current format support).
    :param target_spent_id: an existing spent to attach the bill's items
        to, if already known.
    :param account_id: which account to post a brand-new spent to if no
        ``target_spent_id`` is given and no single existing spent
        obviously matches; required unless ``target_spent_id`` is given.
    :param user: the authenticated user.
    :param import_service: import service.
    :raises HTTPException: 400, if neither ``target_spent_id`` nor
        ``account_id`` is given; 413, if the file is too large.
    :return: the created job, ``status=pending``.
    """
    content = await file.read(settings.imports_max_file_size_bytes + 1)
    try:
        job = await import_service.start_bill_import(
            cast(User, user.unwrap()),
            content,
            file.filename or "upload",
            target_spent_id=target_spent_id,
            account_id=account_id,
        )
    except BillAccountRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Send either target_spent_id or account_id with a bill upload.",
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File is too large.",
        ) from exc
    await process_bill_import.kiq(job.id, account_id)
    return job


@router.get("", response_model=list[ImportJobRead])
async def list_imports(
    user: RequestUser = Depends(require_auth),
    import_service: ImportService = Depends(get_import_service),
) -> list[ImportJob]:
    """
    List the current user's import jobs.

    Always "me"-scoped -- a statement/bill upload is never family-visible.

    :param user: the authenticated user.
    :param import_service: import service.
    :return: matching jobs.
    """
    return await import_service.list_for_user(cast(User, user.unwrap()))


@router.get("/{job_id}", response_model=ImportJobRead)
async def get_import(
    job_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    import_service: ImportService = Depends(get_import_service),
) -> ImportJob:
    """
    Poll an import job's status/counts/error message.

    :param job_id: job to fetch.
    :param user: the authenticated user.
    :param import_service: import service.
    :raises HTTPException: 404, if the job isn't the user's.
    :return: the job.
    """
    try:
        return await import_service.get_owned(cast(User, user.unwrap()), job_id)
    except ImportJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found."
        ) from exc


@router.get("/{job_id}/transactions", response_model=list[ImportedTransactionRead])
async def list_import_transactions(
    job_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    import_service: ImportService = Depends(get_import_service),
) -> list[ImportedTransaction]:
    """
    List the parsed rows belonging to an import job.

    :param job_id: parent job.
    :param user: the authenticated user.
    :param import_service: import service.
    :raises HTTPException: 404, if the job isn't the user's.
    :return: the job's parsed rows.
    """
    try:
        return await import_service.list_transactions(cast(User, user.unwrap()), job_id)
    except ImportJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found."
        ) from exc
