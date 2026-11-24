import asyncio
import io
import uuid
from decimal import Decimal
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette import status

from app.config.settings import settings
from app.dal.category_query import CategoryQuery
from app.dal.user_query import UserQuery
from app.db.sql.models.enums import (
    CategoryKind,
    ImportedTransactionStatus,
    ImportStatus,
)
from app.db.sql.models.users import User
from app.services.import_service import BillAccountRequiredError, ImportService
from app.services.imports.storage import ImportFileStore
from app.services.income_service import IncomeService
from app.services.spent_service import SpentService


def _second_client(fastapi_app: FastAPI) -> AsyncClient:
    """Build another client against the same app, with its own cookie jar."""
    return AsyncClient(
        transport=ASGITransport(fastapi_app), base_url="http://test", timeout=2.0
    )


_WISE_CSV = (
    "TransferWise ID,Date,Amount,Currency,Description,Payee Name\n"
    "TX-1,2026-01-05,-45.00,EUR,Lidl Groceries,Lidl\n"
    "TX-2,2026-02-10,1500.00,EUR,Salary,Employer Inc\n"
)
_WISE_CSV_WITH_BAD_ROW = _WISE_CSV + "TX-3,not-a-date,10.00,EUR,Bad row,Someone\n"


async def _register_and_login(client: AsyncClient, email: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    return uuid.UUID(response.json()["id"])


async def _create_account(
    client: AsyncClient, *, source: str | None = "wise", kind: str = "bank"
) -> uuid.UUID:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Wise EUR", "kind": kind, "currency": "EUR", "source": source},
    )
    return uuid.UUID(response.json()["id"])


async def _category_id(client: AsyncClient, kind: str, name: str) -> int:
    response = await client.get("/api/v1/categories", params={"kind": kind})
    category_id: int = next(c["id"] for c in response.json() if c["name"] == name)
    return category_id


def _make_text_pdf(lines: list[str]) -> bytes:
    """Build a minimal single-page, text-layer PDF for parser tests."""
    content_lines = ["BT", "/F1 12 Tf", "10 380 Td"]
    for index, line in enumerate(lines):
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        if index != 0:
            content_lines.append("0 -14 Td")
        content_lines.append(f"({escaped}) Tj")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
            b"/MediaBox [0 0 300 500] /Contents 4 0 R >>"
        ),
        (b"<< /Length %d >>\nstream\n" % len(content)) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    buf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(buf)
    buf += f"xref\n0 {len(objects) + 1}\n".encode()
    buf += b"0000000000 65535 f \n"
    for offset in offsets:
        buf += f"{offset:010d} 00000 n \n".encode()
    buf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    ).encode()
    return bytes(buf)


_RECEIPT_PDF = _make_text_pdf(
    [
        "Lidl Supermarket",
        "2026-01-15",
        "Milk 1 L    2.38",
        "Bananas    1.99",
        "Total    4.37",
    ]
)


async def test_statement_import_posts_one_row_per_transaction(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """Each CSV row becomes its own dated Spent/Income on the chosen account."""
    user_id = await _register_and_login(client, "imp1@example.com")
    account_id = await _create_account(client)
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    upload = await client.post(
        "/api/v1/imports/statements",
        data={"account_id": str(account_id)},
        files={"file": ("statement.csv", _WISE_CSV, "text/csv")},
    )
    assert upload.status_code == status.HTTP_202_ACCEPTED
    job_id = uuid.UUID(upload.json()["id"])
    assert upload.json()["status"] == "pending"

    await ImportService(dbsession, import_file_store).process_statement_import(job_id)

    job = await client.get(f"/api/v1/imports/{job_id}")
    assert job.json()["status"] == "completed"
    assert job.json()["imported_count"] == 2
    assert job.json()["duplicate_count"] == 0
    assert job.json()["failed_count"] == 0

    rows = await client.get(f"/api/v1/imports/{job_id}/transactions")
    statuses = {row["status"] for row in rows.json()}
    assert statuses == {"imported"}

    spent_service = SpentService(dbsession)
    spents = await spent_service.list_spents(actor)
    assert len(spents) == 1
    assert spents[0].amount == Decimal("45.00")
    assert spents[0].spent_at.isoformat() == "2026-01-05"
    assert spents[0].account_id == account_id

    incomes = await IncomeService(dbsession).list_incomes(actor)
    assert len(incomes) == 1
    assert incomes[0].amount == Decimal("1500.00")
    assert incomes[0].received_at.isoformat() == "2026-02-10"


async def test_statement_import_is_safe_to_reupload(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """Uploading an overlapping export again doesn't double-count rows."""
    user_id = await _register_and_login(client, "imp2@example.com")
    account_id = await _create_account(client)
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    import_service = ImportService(dbsession, import_file_store)
    first_job = await import_service.start_statement_import(
        actor, account_id, _WISE_CSV.encode(), "statement.csv"
    )
    await import_service.process_statement_import(first_job.id)

    second_job = await import_service.start_statement_import(
        actor, account_id, _WISE_CSV.encode(), "statement.csv"
    )
    await import_service.process_statement_import(second_job.id)

    reloaded = await import_service.get_owned(actor, second_job.id)
    assert reloaded.status == ImportStatus.COMPLETED
    assert reloaded.imported_count == 0
    assert reloaded.duplicate_count == 2

    spent_service = SpentService(dbsession)
    assert len(await spent_service.list_spents(actor)) == 1


async def test_statement_import_records_unparseable_rows(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """A row with a bad date is recorded as FAILED, not dropped or crashed on."""
    user_id = await _register_and_login(client, "imp3@example.com")
    account_id = await _create_account(client)
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    import_service = ImportService(dbsession, import_file_store)
    job = await import_service.start_statement_import(
        actor, account_id, _WISE_CSV_WITH_BAD_ROW.encode(), "statement.csv"
    )
    await import_service.process_statement_import(job.id)

    reloaded = await import_service.get_owned(actor, job.id)
    assert reloaded.imported_count == 2
    assert reloaded.failed_count == 1

    rows = await import_service.list_transactions(actor, job.id)
    failed = next(r for r in rows if r.status == ImportedTransactionStatus.FAILED)
    assert "not-a-date" in failed.raw_payload["raw_text"]


async def test_statement_import_rejects_foreign_account(
    client: AsyncClient, fastapi_app: FastAPI
) -> None:
    """Starting an import against an account the actor doesn't own is rejected."""
    async with _second_client(fastapi_app) as owner_client:
        await _register_and_login(owner_client, "imp4a@example.com")
        foreign_account_id = await _create_account(owner_client)

    await _register_and_login(client, "imp4b@example.com")

    response = await client.post(
        "/api/v1/imports/statements",
        data={"account_id": str(foreign_account_id)},
        files={"file": ("statement.csv", _WISE_CSV, "text/csv")},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_statement_import_rejects_account_without_source(
    client: AsyncClient,
) -> None:
    """An account with no configured import source can't be imported into."""
    await _register_and_login(client, "imp5@example.com")
    cash_account_id = await _create_account(client, source=None, kind="cash")

    response = await client.post(
        "/api/v1/imports/statements",
        data={"account_id": str(cash_account_id)},
        files={"file": ("statement.csv", _WISE_CSV, "text/csv")},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_statement_import_rejects_oversized_file(client: AsyncClient) -> None:
    """A file over the configured size limit is rejected before parsing."""
    await _register_and_login(client, "imp6@example.com")
    account_id = await _create_account(client)
    oversized = b"x" * (settings.imports_max_file_size_bytes + 1)

    response = await client.post(
        "/api/v1/imports/statements",
        data={"account_id": str(account_id)},
        files={"file": ("statement.csv", oversized, "text/csv")},
    )

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_bill_import_attaches_to_target_spent(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """A bill uploaded with a target_spent_id attaches its items there."""
    user_id = await _register_and_login(client, "imp7@example.com")
    account_id = await _create_account(client)
    category_id = await _category_id(client, "expense", "Groceries")
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    created = await client.post(
        "/api/v1/spents",
        json={
            "account_id": str(account_id),
            "category_id": category_id,
            "amount": "4.37",
            "spent_at": "2026-01-15",
        },
    )
    spent_id = uuid.UUID(created.json()["id"])

    import_service = ImportService(dbsession, import_file_store)
    job = await import_service.start_bill_import(
        actor, _RECEIPT_PDF, "receipt.pdf", target_spent_id=spent_id
    )
    await import_service.process_bill_import(job.id)

    reloaded = await import_service.get_owned(actor, job.id)
    assert reloaded.status == ImportStatus.COMPLETED
    assert reloaded.imported_count == 2
    assert reloaded.target_spent_id == spent_id

    items = await SpentService(dbsession).list_items(actor, spent_id)
    assert {item.name for item in items} == {"Milk 1 L", "Bananas"}


async def test_bill_import_auto_matches_single_candidate(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """With no target, a single same-day/same-amount spent is used automatically."""
    user_id = await _register_and_login(client, "imp8@example.com")
    account_id = await _create_account(client)
    category_id = await _category_id(client, "expense", "Groceries")
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    created = await client.post(
        "/api/v1/spents",
        json={
            "account_id": str(account_id),
            "category_id": category_id,
            "amount": "4.37",
            "spent_at": "2026-01-15",
        },
    )
    spent_id = uuid.UUID(created.json()["id"])

    import_service = ImportService(dbsession, import_file_store)
    job = await import_service.start_bill_import(
        actor, _RECEIPT_PDF, "receipt.pdf", account_id=account_id
    )
    await import_service.process_bill_import(job.id)

    reloaded = await import_service.get_owned(actor, job.id)
    assert reloaded.status == ImportStatus.COMPLETED
    assert reloaded.target_spent_id == spent_id


async def test_bill_import_creates_new_spent_when_no_match(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """With no match and an account_id, a brand-new spent is created."""
    user_id = await _register_and_login(client, "imp9@example.com")
    account_id = await _create_account(client)
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    import_service = ImportService(dbsession, import_file_store)
    job = await import_service.start_bill_import(
        actor, _RECEIPT_PDF, "receipt.pdf", account_id=account_id
    )
    await import_service.process_bill_import(job.id, account_id)

    reloaded = await import_service.get_owned(actor, job.id)
    assert reloaded.status == ImportStatus.COMPLETED
    assert reloaded.target_spent_id is not None

    spent_service = SpentService(dbsession)
    new_spent = await spent_service.get_visible(actor, reloaded.target_spent_id)
    assert new_spent.amount == Decimal("4.37")
    assert new_spent.account_id == account_id
    groceries_id = await CategoryQuery(dbsession).get_builtin(
        "Groceries", CategoryKind.EXPENSE
    )
    assert new_spent.category_id == cast(int, groceries_id.id if groceries_id else None)


async def test_bill_upload_without_target_or_account_rejected(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """A bill needs either target_spent_id or account_id, checked at upload."""
    user_id = await _register_and_login(client, "imp10@example.com")
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    with pytest.raises(BillAccountRequiredError):
        await ImportService(dbsession, import_file_store).start_bill_import(
            actor, _RECEIPT_PDF, "receipt.pdf"
        )

    response = await client.post(
        "/api/v1/imports/bills", files={"file": ("r.pdf", _RECEIPT_PDF)}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_bill_import_rejects_photo_upload(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """A file that is neither a PDF nor a supported image fails the job."""
    user_id = await _register_and_login(client, "imp11@example.com")
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))

    import_service = ImportService(dbsession, import_file_store)
    job = await import_service.start_bill_import(
        actor, b"not-a-real-image", "receipt.jpg", account_id=uuid.uuid4()
    )
    await import_service.process_bill_import(job.id)

    reloaded = await import_service.get_owned(actor, job.id)
    assert reloaded.status == ImportStatus.FAILED
    assert reloaded.error_message is not None
    assert "PNG, JPEG, WebP and HEIC" in reloaded.error_message


async def test_bill_import_fails_for_unowned_target_spent(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    import_file_store: ImportFileStore,
) -> None:
    """A target_spent_id belonging to someone else fails the job, not a crash."""
    async with _second_client(fastapi_app) as owner_client:
        await _register_and_login(owner_client, "imp13a@example.com")
        owner_account_id = await _create_account(owner_client)
        category_id = await _category_id(owner_client, "expense", "Groceries")
        created = await owner_client.post(
            "/api/v1/spents",
            json={
                "account_id": str(owner_account_id),
                "category_id": category_id,
                "amount": "4.37",
                "spent_at": "2026-01-15",
            },
        )
        owner_spent_id = uuid.UUID(created.json()["id"])

    other_user_id = await _register_and_login(client, "imp13b@example.com")
    actor = cast(User, await UserQuery(dbsession).get_by_id(other_user_id))

    import_service = ImportService(dbsession, import_file_store)
    job = await import_service.start_bill_import(
        actor, _RECEIPT_PDF, "receipt.pdf", target_spent_id=owner_spent_id
    )
    await import_service.process_bill_import(job.id)

    reloaded = await import_service.get_owned(actor, job.id)
    assert reloaded.status == ImportStatus.FAILED
    assert reloaded.error_message == "Target spent not found."


async def test_list_imports_scoped_to_me(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """Import jobs never leak across users, family or not."""
    user1_id = await _register_and_login(client, "imp12a@example.com")
    actor1 = cast(User, await UserQuery(dbsession).get_by_id(user1_id))
    await ImportService(dbsession, import_file_store).start_bill_import(
        actor1, _RECEIPT_PDF, "r.pdf", account_id=uuid.uuid4()
    )

    await client.post("/api/v1/auth/logout")
    await _register_and_login(client, "imp12b@example.com")

    response = await client.get("/api/v1/imports")
    assert response.json() == []


async def test_file_is_removed_once_worker_takes_it(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """Processing a bill consumes its stored file, success or not."""
    user_id = await _register_and_login(client, "imp_clean1@example.com")
    account_id = await _create_account(client)
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))
    service = ImportService(dbsession, import_file_store)
    ok_job = await service.start_bill_import(
        actor, _RECEIPT_PDF, "receipt.pdf", account_id=account_id
    )
    bad_job = await service.start_bill_import(
        actor, b"not a bill", "bill.txt", account_id=account_id
    )

    await service.process_bill_import(ok_job.id, account_id)
    await service.process_bill_import(bad_job.id)

    assert await import_file_store.pop(ok_job.id) is None
    assert await import_file_store.pop(bad_job.id) is None
    failed = await service.get_owned(actor, bad_job.id)
    assert failed.status == ImportStatus.FAILED


async def test_expired_file_fails_the_job(
    client: AsyncClient, dbsession: AsyncSession, import_file_store: ImportFileStore
) -> None:
    """A job whose upload expired before the worker ran is marked failed."""
    user_id = await _register_and_login(client, "imp_clean2@example.com")
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))
    service = ImportService(dbsession, import_file_store)
    job = await service.start_bill_import(
        actor, _RECEIPT_PDF, "receipt.pdf", account_id=uuid.uuid4()
    )
    await import_file_store.pop(job.id)

    await service.process_bill_import(job.id)

    reloaded = await service.get_owned(actor, job.id)
    assert reloaded.status == ImportStatus.FAILED
    assert reloaded.error_message is not None


async def test_concurrent_uploads_keep_their_own_files(
    import_file_store: ImportFileStore,
) -> None:
    """Many simultaneous saves never mix up or lose each other's bytes."""
    ids = [uuid.uuid4() for _ in range(20)]

    await asyncio.gather(
        *(import_file_store.save(i, str(i).encode() * 1000) for i in ids)
    )
    popped = await asyncio.gather(*(import_file_store.pop(i) for i in ids))
    again = await asyncio.gather(*(import_file_store.pop(i) for i in ids))

    assert popped == [str(i).encode() * 1000 for i in ids]
    assert again == [None] * len(ids)


async def test_bill_photo_without_llm_key_fails_with_message(
    client: AsyncClient,
    dbsession: AsyncSession,
    import_file_store: ImportFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A photo needs the vision model; without a key the job says so."""
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    user_id = await _register_and_login(client, "imp_photo@example.com")
    actor = cast(User, await UserQuery(dbsession).get_by_id(user_id))
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), "white").save(buffer, "PNG")
    service = ImportService(dbsession, import_file_store)
    job = await service.start_bill_import(
        actor, buffer.getvalue(), "receipt.png", account_id=uuid.uuid4()
    )

    await service.process_bill_import(job.id)

    reloaded = await service.get_owned(actor, job.id)
    assert reloaded.status == ImportStatus.FAILED
    assert reloaded.error_message
    assert "not configured" in reloaded.error_message
