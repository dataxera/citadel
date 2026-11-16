# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from unittest.mock import AsyncMock, MagicMock

import fastapi
import pytest

from citadel.fw import model as fw_model
from citadel.fw.model import AsyncSession


@pytest.mark.asyncio
async def test_session_commits_before_http_response_is_sent(monkeypatch):
    """Verify AsyncSession commits before FastAPI sends the HTTP response."""
    events: list[str] = []

    mock_session = MagicMock()

    async def fake_commit():
        events.append("commit")

    mock_session.commit = AsyncMock(side_effect=fake_commit)

    class FakeSessionCtx:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(fw_model, "SQLModelAsyncSession", lambda engine: FakeSessionCtx())
    monkeypatch.setattr(fw_model, "get_engine", lambda: MagicMock())

    test_app = fastapi.FastAPI()

    @test_app.post("/items")
    async def create_item(session: AsyncSession):
        events.append("handler")
        return {"status": "ok"}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            events.append("http.response.start")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/items",
        "raw_path": b"/items",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await test_app(scope, receive, send)

    assert "handler" in events
    assert "commit" in events
    assert "http.response.start" in events
    assert events.index("commit") < events.index("http.response.start"), (
        f"Expected session.commit() before http.response.start, got order: {events}"
    )
