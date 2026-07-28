# -*- coding: utf-8 -*-

"""Deterministic HTTP tests for the OpenAI Codex subscription backend."""

from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from deep_research_mcp.backends.codex_backend import (
    CODEX_PROTOCOL_VERSION,
    CodexResearchBackend,
)
from deep_research_mcp.codex_auth import (
    CodexAuthEndpoints,
    CodexAuthManager,
)
from deep_research_mcp.config import OPENAI_CODEX_BASE_URL, ResearchConfig


def _jwt(*, expires_at: float, account_id: str = "account-123") -> str:
    header = _b64_json({"alg": "none", "typ": "JWT"})
    payload = _b64_json(
        {
            "exp": expires_at,
            "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
        }
    )
    return f"{header}.{payload}."


def _b64_json(value: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    )
    return encoded.decode().rstrip("=")


def _sse(*events: dict[str, object] | str) -> bytes:
    lines: list[str] = []
    for event in events:
        data = event if isinstance(event, str) else json.dumps(event)
        lines.extend([f"data: {data}", ""])
    return "\n".join(lines).encode()


def _completed_stream() -> bytes:
    return _sse(
        {
            "type": "response.created",
            "response": {"id": "resp-codex-123", "output": None},
        },
        {
            "type": "response.output_item.done",
            "item": {"id": "reason-1", "type": "reasoning"},
        },
        {
            "type": "response.output_item.done",
            "item": {
                "id": "search-1",
                "type": "web_search_call",
                "action": {"type": "search", "query": "current evidence"},
            },
        },
        {
            "type": "response.output_text.delta",
            "delta": "A researched answer with a source.",
        },
        {
            "type": "response.output_text.annotation.added",
            "annotation": {
                "type": "url_citation",
                "title": "Evidence",
                "url": "https://example.com/evidence",
            },
        },
        {
            "type": "response.output_item.done",
            "item": {
                "id": "message-1",
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "A researched answer with a source.",
                    }
                ],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-codex-123",
                "status": "completed",
                "output": None,
            },
        },
        "[DONE]",
    )


@pytest.fixture
def codex_backend_server():
    """Serve account models, response streams, and refresh tokens locally."""
    state: dict[str, object] = {
        "mode": "completed",
        "models": [
            {"slug": "gpt-hidden", "visibility": "hide"},
            {"slug": "gpt-picker", "visibility": "list"},
        ],
        "last_headers": {},
        "last_model_query": {},
        "last_request": {},
        "response_calls": 0,
        "model_calls": 0,
        "refresh_count": 0,
        "model_401_once": False,
        "response_401_once": False,
        "model_401_always": False,
        "response_401_always": False,
    }

    class CodexBackendHandler(BaseHTTPRequestHandler):
        """Handle real local Codex backend requests for the test fixture."""

        def do_GET(self):
            parsed_url = urlsplit(self.path)
            if parsed_url.path != "/models":
                self._json(404, {"error": "not_found"})
                return
            model_query = parse_qs(parsed_url.query)
            state["last_model_query"] = model_query
            if model_query != {"client_version": [CODEX_PROTOCOL_VERSION]}:
                self._json(
                    400,
                    {
                        "detail": [
                            {
                                "type": "missing",
                                "loc": ["query", "client_version"],
                            }
                        ]
                    },
                )
                return
            state["model_calls"] = int(state["model_calls"]) + 1
            state["last_headers"] = dict(self.headers)
            if state["model_401_always"] or (
                state["model_401_once"] and state["model_calls"] == 1
            ):
                self._json(401, {"error": {"message": "expired"}})
                return
            self._json(200, {"models": state["models"]})

        def do_POST(self):  # pylint: disable=too-many-return-statements
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)

            if self.path == "/oauth-token":
                request = json.loads(body)
                assert request["grant_type"] == "refresh_token"
                state["refresh_count"] = int(state["refresh_count"]) + 1
                self._json(
                    200,
                    {
                        "access_token": _jwt(expires_at=time.time() + 3600),
                        "refresh_token": "refresh-rotated",
                    },
                )
                return

            if self.path != "/responses":
                self._json(404, {"error": "not_found"})
                return

            state["response_calls"] = int(state["response_calls"]) + 1
            state["last_headers"] = dict(self.headers)
            state["last_request"] = json.loads(body)
            if state["response_401_always"] or (
                state["response_401_once"] and state["response_calls"] == 1
            ):
                self._json(401, {"error": {"message": "expired"}})
                return
            if state["mode"] == "forbidden":
                self._json(403, {"error": {"message": "originator rejected"}})
                return
            if state["mode"] == "rate_limited":
                self._json(429, {"error": {"message": "limit reached"}})
                return
            if state["mode"] == "malformed":
                self._stream(_sse("not-json", "[DONE]"))
                return
            if state["mode"] == "truncated":
                self._stream(
                    _sse(
                        {
                            "type": "response.output_text.delta",
                            "delta": "partial",
                        },
                        "[DONE]",
                    )
                )
                return
            self._stream(_completed_stream())

        def log_message(self, format, *args):  # pylint: disable=redefined-builtin
            del format, args

        def _json(self, status_code: int, data: dict[str, object]) -> None:
            payload = json.dumps(data).encode()
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _stream(self, payload: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), CodexBackendHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _write_auth(
    path: Path,
    *,
    access_token: str | None = None,
    refresh_token: str = "refresh-initial",
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "access_token": access_token or _jwt(expires_at=time.time() + 3600),
                "refresh_token": refresh_token,
                "account_id": "account-123",
                "expires_at": time.time() + 3600,
                "source": "device",
            }
        ),
        encoding="utf-8",
    )


def _backend(
    tmp_path: Path,
    base_url: str,
    *,
    model: str = "auto",
    endpoints: CodexAuthEndpoints | None = None,
) -> CodexResearchBackend:
    auth_path = tmp_path / "auth.json"
    _write_auth(auth_path)
    manager = CodexAuthManager(
        store_path=auth_path,
        endpoints=endpoints,
    )
    config = ResearchConfig(
        provider="openai-codex",
        model=model,
        base_url=OPENAI_CODEX_BASE_URL,
        timeout=5,
    )
    return CodexResearchBackend(
        config,
        logging.getLogger("codex-backend-test"),
        auth_manager=manager,
        base_url=base_url,
    )


@pytest.mark.asyncio
async def test_codex_backend_discovers_model_and_assembles_sse(
    tmp_path: Path, codex_backend_server
):
    base_url, state = codex_backend_server
    backend = _backend(tmp_path, base_url)

    task_started: list[str] = []

    async def record_task_started(task_id: str) -> None:
        task_started.append(task_id)

    result = await backend.research(
        "Research this",
        system_prompt="Prefer primary sources.",
        include_code_interpreter=True,
        on_task_started=record_task_started,
    )

    assert result.status == "completed"
    assert result.task_id == "resp-codex-123"
    assert result.final_report == "A researched answer with a source."
    assert result.reasoning_steps == 1
    assert result.search_queries == ["current evidence"]
    assert result.total_steps == 3
    assert result.citations[0].title == "Evidence"
    assert result.citations[0].url == "https://example.com/evidence"
    assert result.message is not None
    assert "Code Interpreter is not available" in result.message

    headers = state["last_headers"]
    request = state["last_request"]
    assert isinstance(headers, dict)
    assert isinstance(request, dict)
    assert headers["ChatGPT-Account-ID"] == "account-123"
    assert headers["originator"] == "deep_research_mcp"
    assert headers["User-Agent"].startswith("deep-research-mcp/")
    assert state["last_model_query"] == {"client_version": [CODEX_PROTOCOL_VERSION]}
    assert request["model"] == "gpt-picker"
    assert request["stream"] is True
    assert request["store"] is False
    assert request["tools"] == [{"type": "web_search"}]
    assert "Prefer primary sources." in request["instructions"]
    assert not task_started


@pytest.mark.asyncio
async def test_codex_backend_rejects_unavailable_explicit_model(
    tmp_path: Path, codex_backend_server
):
    base_url, state = codex_backend_server
    backend = _backend(tmp_path, base_url, model="not-on-account")

    result = await backend.research("Research this")

    assert result.status == "failed"
    assert result.error_code == "model_not_available"
    assert "gpt-picker" in str(result.message)
    assert state["response_calls"] == 0


@pytest.mark.asyncio
async def test_codex_backend_rejects_truncated_stream(
    tmp_path: Path, codex_backend_server
):
    base_url, state = codex_backend_server
    state["mode"] = "truncated"
    backend = _backend(tmp_path, base_url)

    result = await backend.research("Research this", include_code_interpreter=False)

    assert result.status == "failed"
    assert result.error_code == "truncated_stream"
    assert "terminal response" in str(result.message)


@pytest.mark.asyncio
async def test_codex_backend_explains_rejected_originator(
    tmp_path: Path, codex_backend_server
):
    base_url, state = codex_backend_server
    state["mode"] = "forbidden"
    backend = _backend(tmp_path, base_url)

    result = await backend.research("Research this", include_code_interpreter=False)

    assert result.status == "failed"
    assert result.error_code == "access_denied"
    assert "third-party client" in str(result.message)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "error_code"),
    [
        ("rate_limited", "rate_limited"),
        ("malformed", "invalid_stream"),
    ],
)
async def test_codex_backend_reports_protocol_and_limit_failures(
    tmp_path: Path, codex_backend_server, mode: str, error_code: str
):
    base_url, state = codex_backend_server
    state["mode"] = mode
    backend = _backend(tmp_path, base_url)

    result = await backend.research("Research this", include_code_interpreter=False)

    assert result.status == "failed"
    assert result.error_code == error_code


@pytest.mark.asyncio
async def test_codex_backend_refreshes_once_after_model_401(
    tmp_path: Path, codex_backend_server
):
    base_url, state = codex_backend_server
    state["model_401_once"] = True
    auth_path = tmp_path / "auth.json"
    _write_auth(auth_path, access_token=_jwt(expires_at=time.time() + 3600))
    endpoints = CodexAuthEndpoints(oauth_token_url=f"{base_url}/oauth-token")
    manager = CodexAuthManager(store_path=auth_path, endpoints=endpoints)
    config = ResearchConfig(
        provider="openai-codex",
        model="auto",
        base_url=OPENAI_CODEX_BASE_URL,
        timeout=5,
    )
    backend = CodexResearchBackend(
        config,
        logging.getLogger("codex-backend-refresh-test"),
        auth_manager=manager,
        base_url=base_url,
    )

    result = await backend.research("Research this", include_code_interpreter=False)

    assert result.status == "completed"
    assert state["model_calls"] == 2
    assert state["refresh_count"] == 1


@pytest.mark.asyncio
async def test_codex_backend_refreshes_once_after_response_401(
    tmp_path: Path, codex_backend_server
):
    base_url, state = codex_backend_server
    state["response_401_once"] = True
    auth_path = tmp_path / "auth.json"
    _write_auth(auth_path)
    endpoints = CodexAuthEndpoints(oauth_token_url=f"{base_url}/oauth-token")
    manager = CodexAuthManager(store_path=auth_path, endpoints=endpoints)
    config = ResearchConfig(
        provider="openai-codex",
        model="auto",
        base_url=OPENAI_CODEX_BASE_URL,
        timeout=5,
    )
    backend = CodexResearchBackend(
        config,
        logging.getLogger("codex-backend-response-refresh-test"),
        auth_manager=manager,
        base_url=base_url,
    )

    result = await backend.research("Research this", include_code_interpreter=False)

    assert result.status == "completed"
    assert state["response_calls"] == 2
    assert state["refresh_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["model", "response"])
async def test_codex_backend_stops_after_refreshed_token_is_rejected(
    tmp_path: Path, codex_backend_server, endpoint: str
):
    base_url, state = codex_backend_server
    state[f"{endpoint}_401_always"] = True
    endpoints = CodexAuthEndpoints(oauth_token_url=f"{base_url}/oauth-token")
    backend = _backend(tmp_path, base_url, endpoints=endpoints)

    result = await backend.research("Research this", include_code_interpreter=False)

    assert result.status == "failed"
    assert result.error_code == "authentication_failed"
    assert state[f"{endpoint}_calls"] == 2
    assert state["refresh_count"] == 1


@pytest.mark.asyncio
async def test_codex_task_status_is_explicitly_unsupported(
    tmp_path: Path, codex_backend_server
):
    base_url, _ = codex_backend_server
    backend = _backend(tmp_path, base_url)

    status = await backend.get_task_status("resp-codex-123")

    assert status.status == "unknown"
    assert "not available" in str(status.message)
    assert await backend.get_task_result("resp-codex-123") is None
