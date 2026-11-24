import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.statement_source_service import (
    StatementSourceConflictError,
    StatementSourceInvalidNameError,
    StatementSourceNotFoundError,
    StatementSourceService,
)


async def test_create_and_retrieve(dbsession: AsyncSession) -> None:
    """A created source can be fetched back by id."""
    service = StatementSourceService(dbsession)

    created = await service.create("Monese")
    fetched = await service.retrieve(created.id or 0)

    assert fetched.name == "Monese"


async def test_list_is_ordered_by_name(dbsession: AsyncSession) -> None:
    """Sources come back sorted by name."""
    service = StatementSourceService(dbsession)
    await service.create("Zeta")
    await service.create("Alpha")

    names = [s.name for s in await service.list_sources()]

    assert names == sorted(names)
    assert {"Alpha", "Zeta"} <= set(names)


async def test_duplicate_name_is_rejected(dbsession: AsyncSession) -> None:
    """Names are unique."""
    service = StatementSourceService(dbsession)
    await service.create("Monzo")

    with pytest.raises(StatementSourceConflictError):
        await service.create("Monzo")


async def test_retrieve_missing_raises(dbsession: AsyncSession) -> None:
    """Retrieving an unknown id raises."""
    with pytest.raises(StatementSourceNotFoundError):
        await StatementSourceService(dbsession).retrieve(999_999)


async def test_code_sanitizes_name(dbsession: AsyncSession) -> None:
    """The code is lower-case with special symbols turned into underscores."""
    source = await StatementSourceService(dbsession).create("Bank of A.B. (EU)")

    assert source.code == "bank_of_a_b_eu"


@pytest.mark.parametrize("name", ["\u0421\u0431\u0435\u0440", "Bänk", "12345", ""])
async def test_non_latin_name_is_rejected(dbsession: AsyncSession, name: str) -> None:
    """Names must be latin (and contain at least one letter)."""
    with pytest.raises(StatementSourceInvalidNameError):
        await StatementSourceService(dbsession).create(name)
