from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import require_auth
from app.api.dependencies.permissions import require_superuser
from app.api.dependencies.statement_sources import get_statement_source_service
from app.api.v1.statement_sources.schema import (
    StatementSourceCreate,
    StatementSourceRead,
)
from app.db.sql.models.statement_source import StatementSourceRecord
from app.services.statement_source_service import (
    StatementSourceConflictError,
    StatementSourceInvalidNameError,
    StatementSourceNotFoundError,
    StatementSourceService,
)

router = APIRouter(
    prefix="/statement-sources",
    tags=["statement-sources"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[StatementSourceRead])
async def list_statement_sources(
    service: StatementSourceService = Depends(get_statement_source_service),
) -> list[StatementSourceRecord]:
    """
    List every statement source.

    :param service: statement-source service.
    :return: all sources, ordered by name.
    """
    return await service.list_sources()


@router.get("/{source_id}", response_model=StatementSourceRead)
async def retrieve_statement_source(
    source_id: int,
    service: StatementSourceService = Depends(get_statement_source_service),
) -> StatementSourceRecord:
    """
    Fetch one statement source.

    :param source_id: source id.
    :param service: statement-source service.
    :raises HTTPException: 404, if it doesn't exist.
    :return: the source.
    """
    try:
        return await service.retrieve(source_id)
    except StatementSourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Statement source not found."
        ) from exc


@router.post(
    "",
    response_model=StatementSourceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superuser)],
)
async def create_statement_source(
    payload: StatementSourceCreate,
    service: StatementSourceService = Depends(get_statement_source_service),
) -> StatementSourceRecord:
    """
    Create a statement source (superusers only).

    :param payload: statement-source creation payload.
    :param service: statement-source service.
    :raises HTTPException: 400 for a non-latin name, 409 for a taken name.
    :return: the created source.
    """
    try:
        return await service.create(payload.name)
    except StatementSourceInvalidNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must use latin symbols only.",
        ) from exc
    except StatementSourceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A statement source with this name already exists.",
        ) from exc
