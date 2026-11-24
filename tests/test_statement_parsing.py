import base64
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette import status

from app.api.dependencies.statement_parsing import get_openrouter_client
from app.api.v1.statement_parsing import routes
from app.libs.openrouter.client import OpenRouterError
from app.libs.redis.client import RedisClient
from app.services.pending_transaction_cache import PendingTransactionCache
from app.services.statement_parse_service import StatementParseService

PASSWORD = "correct horse battery staple"  # noqa: S105
_PDF = b"%PDF-1.4 fake statement"
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


class _FakeLLM:
    """Stands in for OpenRouter, replying with a canned JSON document."""

    def __init__(self) -> None:
        self.reply = ""
        self.calls: list[list[dict[str, Any]]] = []

    async def complete_json(self, messages: list[dict[str, Any]], **_: Any) -> str:
        self.calls.append(messages)
        if self.reply == "ERROR":
            raise OpenRouterError("boom")
        return self.reply


class _InlineTask:
    """Runs the background task inline, in the test's own db session."""

    def __init__(
        self, session: AsyncSession, cache: PendingTransactionCache, llm: _FakeLLM
    ) -> None:
        self.session = session
        self.cache = cache
        self.llm = llm

    async def kiq(self, job_id: uuid.UUID, files: list[tuple[str, str]]) -> None:
        service = StatementParseService(
            self.session,
            self.cache,
            self.llm,  # type: ignore[arg-type]
        )
        await service.process(
            job_id, [(name, base64.b64decode(data)) for name, data in files]
        )


@pytest.fixture
async def llm(
    fastapi_app: FastAPI,
    test_redis_client: RedisClient,
    dbsession: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[_FakeLLM, None]:
    """Install a fake OpenRouter client, redis, and an inline background task."""
    fake = _FakeLLM()
    fastapi_app.state.redis_client = test_redis_client
    fastapi_app.dependency_overrides[get_openrouter_client] = lambda: fake
    monkeypatch.setattr(
        routes,
        "process_statement_parse",
        _InlineTask(dbsession, PendingTransactionCache(test_redis_client), fake),
    )
    yield fake
    fastapi_app.dependency_overrides.pop(get_openrouter_client, None)


def _rows(*rows: dict[str, Any]) -> str:
    return json.dumps({"transactions": list(rows)})


def _row(
    date: str = "2026-09-18",
    amount: str = "63.80",
    direction: str = "expense",
    description: str = "Mesarija Vintar",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "date": date,
        "amount": amount,
        "direction": direction,
        "currency": "EUR",
        "description": description,
        **extra,
    }


async def _login(client: AsyncClient, email: str) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


async def _account(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/accounts", json={"name": "Wise", "kind": "bank", "currency": "EUR"}
    )
    return str(response.json()["id"])


async def _category(client: AsyncClient, kind: str = "expense") -> int:
    listed = await client.get("/api/v1/categories", params={"kind": kind})
    return int(listed.json()[0]["id"])


async def _start(
    client: AsyncClient, files: list[tuple[str, bytes, str]] | None = None, **data: str
) -> Any:
    uploads = [
        ("files", (name, content, ctype))
        for name, content, ctype in files or [("s.pdf", _PDF, "application/pdf")]
    ]
    return await client.post(
        "/api/v1/statement-parsing/parse", files=uploads, data=data
    )


async def _parse(
    client: AsyncClient, files: list[tuple[str, bytes, str]] | None = None, **data: str
) -> dict[str, Any]:
    """Upload, wait for the (inline) job, and collect the job plus its rows."""
    started = await _start(client, files, **data)
    assert started.status_code == status.HTTP_202_ACCEPTED
    job_id = started.json()["id"]
    polled = await client.get(f"/api/v1/statement-parsing/parse/{job_id}/status")
    job: dict[str, Any] = polled.json()
    rows = await client.get(
        "/api/v1/statement-parsing/transactions", params={"job_id": job_id}
    )
    return {**job, "transactions": rows.json()}


async def test_parse_returns_and_caches_transactions(
    client: AsyncClient, llm: _FakeLLM
) -> None:
    """Parsed rows come back, are normalised, and can be collected later."""
    await _login(client, "sp1@example.com")
    category_id = await _category(client)
    llm.reply = _rows(
        _row(amount="-63.80", suggested=1, category_id=category_id),
        _row(date="2026-09-20", amount="300", direction="income", description="Pay"),
        {"date": "garbage", "amount": "1", "direction": "expense"},
    )

    body = await _parse(
        client,
        [("a.pdf", _PDF, "application/pdf"), ("b.png", _PNG, "image/png")],
    )

    assert body["status"] == "completed"
    assert body["transaction_count"] == 2
    assert body["skipped_count"] == 1
    assert body["duplicate_count"] == 0
    second, first = body["transactions"]  # most recent date first
    assert first["amount"] == "63.80"
    assert first["kind"] == "expense"
    assert first["suggested_category_id"] == category_id
    assert second["kind"] == "income"
    assert second["suggested_category_id"] is None

    parts = llm.calls[0][1]["content"]
    assert {p["type"] for p in parts} == {"text", "file", "image_url"}

    pending = await client.get("/api/v1/statement-parsing/transactions")
    assert {t["id"] for t in pending.json()} == {t["id"] for t in body["transactions"]}
    other_job = await client.get(
        "/api/v1/statement-parsing/transactions", params={"job_id": "nope"}
    )
    assert other_job.json() == []


async def test_decline_removes_from_cache(client: AsyncClient, llm: _FakeLLM) -> None:
    """A declined row disappears from the pending list."""
    await _login(client, "sp2@example.com")
    llm.reply = _rows(_row())
    tx_id = (await _parse(client))["transactions"][0]["id"]

    declined = await client.delete(f"/api/v1/statement-parsing/transactions/{tx_id}")
    again = await client.delete(f"/api/v1/statement-parsing/transactions/{tx_id}")

    assert declined.status_code == status.HTTP_204_NO_CONTENT
    assert again.status_code == status.HTTP_404_NOT_FOUND
    pending = await client.get("/api/v1/statement-parsing/transactions")
    assert pending.json() == []


async def test_save_creates_record_and_removes_from_cache(
    client: AsyncClient, llm: _FakeLLM
) -> None:
    """Saving posts a spent with the client's account/category and corrections."""
    await _login(client, "sp3@example.com")
    account_id = await _account(client)
    category_id = await _category(client)
    llm.reply = _rows(_row())
    tx_id = (await _parse(client))["transactions"][0]["id"]

    saved = await client.post(
        f"/api/v1/statement-parsing/transactions/{tx_id}/save",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "description": "Butcher",
        },
    )

    assert saved.status_code == status.HTTP_200_OK
    assert saved.json()["kind"] == "spent"
    spents = await client.get("/api/v1/spents")
    assert [s["description"] for s in spents.json()] == ["Butcher"]
    assert spents.json()[0]["amount"] == "63.80"
    pending = await client.get("/api/v1/statement-parsing/transactions")
    assert pending.json() == []


async def test_save_rejects_category_of_wrong_kind(
    client: AsyncClient, llm: _FakeLLM
) -> None:
    """An income category can't file an expense; the row stays pending."""
    await _login(client, "sp4@example.com")
    account_id = await _account(client)
    income_category = await _category(client, "income")
    llm.reply = _rows(_row())
    tx_id = (await _parse(client))["transactions"][0]["id"]

    response = await client.post(
        f"/api/v1/statement-parsing/transactions/{tx_id}/save",
        json={"account_id": account_id, "category_id": income_category},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    pending = await client.get("/api/v1/statement-parsing/transactions")
    assert len(pending.json()) == 1


async def test_existing_transactions_are_flagged_as_duplicates(
    client: AsyncClient, llm: _FakeLLM
) -> None:
    """Rows matching saved spents are flagged, one-to-one."""
    await _login(client, "sp5@example.com")
    account_id = await _account(client)
    category_id = await _category(client)
    created = await client.post(
        "/api/v1/spents",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount": "63.80",
            "spent_at": "2026-09-18",
        },
    )
    spent_id = created.json()["id"]
    llm.reply = _rows(_row(), _row())

    body = await _parse(client, account_id=account_id)

    assert body["duplicate_count"] == 1
    flagged, fresh = body["transactions"]
    assert flagged["duplicate_of"] == {
        "source": "existing",
        "kind": "spent",
        "id": spent_id,
    }
    assert fresh["duplicate_of"] is None
    assert flagged["account_id"] == account_id


async def test_reuploading_flags_pending_duplicates(
    client: AsyncClient, llm: _FakeLLM
) -> None:
    """The same statement uploaded twice is flagged against the pending rows."""
    await _login(client, "sp6@example.com")
    llm.reply = _rows(_row())
    first = (await _parse(client))["transactions"][0]

    second = await _parse(client)

    assert second["duplicate_count"] == 1
    assert second["transactions"][0]["duplicate_of"] == {
        "source": "pending",
        "kind": "pending",
        "id": first["id"],
    }


async def test_pending_transactions_are_private(
    client: AsyncClient, llm: _FakeLLM, fastapi_app: FastAPI
) -> None:
    """Another user can neither see nor discard someone else's pending rows."""
    await _login(client, "sp7@example.com")
    llm.reply = _rows(_row())
    tx_id = (await _parse(client))["transactions"][0]["id"]

    async with AsyncClient(
        transport=client._transport,  # noqa: SLF001
        base_url="http://test",
    ) as other:
        await _login(other, "sp7b@example.com")
        listed = await other.get("/api/v1/statement-parsing/transactions")
        declined = await other.delete(f"/api/v1/statement-parsing/transactions/{tx_id}")

    assert listed.json() == []
    assert declined.status_code == status.HTTP_404_NOT_FOUND


async def test_upload_validation_fails_fast(client: AsyncClient, llm: _FakeLLM) -> None:
    """Bad uploads are rejected immediately, before any job exists."""
    await _login(client, "sp8@example.com")

    binary = await _start(client, [("x.bin", b"\x00\x01\x02", "application/x")])
    assert binary.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    other_account = await _start(
        client, account_id="00000000-0000-0000-0000-000000000000"
    )
    assert other_account.status_code == status.HTTP_404_NOT_FOUND


async def test_model_failures_end_the_job_as_failed(
    client: AsyncClient, llm: _FakeLLM
) -> None:
    """An unreachable or garbled model reply is reported through the status."""
    await _login(client, "sp9@example.com")

    llm.reply = "ERROR"
    upstream = await _parse(client)
    assert upstream["status"] == "failed"
    assert upstream["error_message"] == "Could not parse the statement."

    llm.reply = "not json"
    garbled = await _parse(client)
    assert garbled["status"] == "failed"
    assert garbled["transactions"] == []


async def test_job_status_is_private(client: AsyncClient, llm: _FakeLLM) -> None:
    """Another user can't poll someone else's job."""
    await _login(client, "sp10@example.com")
    llm.reply = _rows(_row())
    job_id = (await _start(client)).json()["id"]

    async with AsyncClient(
        transport=client._transport,  # noqa: SLF001
        base_url="http://test",
    ) as other:
        await _login(other, "sp10b@example.com")
        response = await other.get(f"/api/v1/statement-parsing/parse/{job_id}/status")

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_start_returns_job_to_poll(client: AsyncClient, llm: _FakeLLM) -> None:
    """The upload answers 202 with the job to poll."""
    await _login(client, "sp11@example.com")
    llm.reply = _rows(_row())
    response = await _start(client)

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["filenames"] == ["s.pdf"]


async def test_parse_requires_auth(client: AsyncClient, llm: _FakeLLM) -> None:
    """Anonymous uploads are rejected."""
    assert (await _start(client)).status_code == status.HTTP_401_UNAUTHORIZED
