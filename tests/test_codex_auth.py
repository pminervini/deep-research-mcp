# -*- coding: utf-8 -*-

"""Tests for the independent OpenAI Codex subscription OAuth session."""

from __future__ import annotations

import asyncio
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import stat
import threading
import time
from urllib.parse import parse_qs

import pytest

from deep_research_mcp.codex_auth import (
    CODEX_OAUTH_CLIENT_ID,
    CodexAuthEndpoints,
    CodexAuthError,
    CodexAuthManager,
    CodexTokens,
)


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


@pytest.fixture
def codex_oauth_server():
    """Serve the real device and refresh HTTP exchanges locally."""
    state: dict[str, object] = {
        "refresh_count": 0,
        "refresh_error": False,
        "authorization_exchange": None,
    }

    class CodexOAuthHandler(BaseHTTPRequestHandler):
        """Handle real local OAuth requests for the test fixture."""

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)

            if self.path == "/device-user-code":
                request = json.loads(body)
                assert request["client_id"] == CODEX_OAUTH_CLIENT_ID
                self._json(
                    200,
                    {
                        "device_auth_id": "device-123",
                        "user_code": "ABCD-EFGH",
                    },
                )
                return

            if self.path == "/device-token":
                request = json.loads(body)
                assert request == {
                    "device_auth_id": "device-123",
                    "user_code": "ABCD-EFGH",
                }
                self._json(
                    200,
                    {
                        "authorization_code": "authorization-123",
                        "code_verifier": "verifier-123",
                    },
                )
                return

            if self.path == "/oauth-token":
                content_type = self.headers.get("Content-Type", "")
                if content_type.startswith("application/json"):
                    request = json.loads(body)
                    assert request["grant_type"] == "refresh_token"
                    state["refresh_count"] = int(state["refresh_count"]) + 1
                    if state["refresh_error"]:
                        self._json(
                            400,
                            {
                                "error": {
                                    "code": "invalid_grant",
                                    "message": "refresh token reused",
                                }
                            },
                        )
                        return
                    self._json(
                        200,
                        {
                            "access_token": _jwt(expires_at=time.time() + 3600),
                            "refresh_token": "refresh-rotated",
                        },
                    )
                    return

                request = parse_qs(body.decode())
                state["authorization_exchange"] = request
                self._json(
                    200,
                    {
                        "access_token": _jwt(expires_at=time.time() + 3600),
                        "refresh_token": "refresh-initial",
                    },
                )
                return

            self._json(404, {"error": "not_found"})

        def log_message(self, format, *args):  # pylint: disable=redefined-builtin
            del format, args

        def _json(self, status_code: int, data: dict[str, object]) -> None:
            payload = json.dumps(data).encode()
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), CodexOAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"
        endpoints = CodexAuthEndpoints(
            user_code_url=f"{base_url}/device-user-code",
            device_token_url=f"{base_url}/device-token",
            oauth_token_url=f"{base_url}/oauth-token",
            verification_url=f"{base_url}/verify",
            redirect_uri=f"{base_url}/callback",
        )
        yield endpoints, state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.asyncio
async def test_device_login_stores_private_independent_credentials(
    tmp_path: Path, codex_oauth_server
):
    endpoints, state = codex_oauth_server
    store_path = tmp_path / "auth.json"
    displayed: list[tuple[str, str]] = []
    manager = CodexAuthManager(
        store_path=store_path,
        endpoints=endpoints,
        poll_interval=0.01,
        device_timeout=1,
    )

    tokens = await manager.login_device(lambda url, code: displayed.append((url, code)))

    assert displayed == [(endpoints.verification_url, "ABCD-EFGH")]
    assert tokens.account_id == "account-123"
    assert tokens.refresh_token == "refresh-initial"
    assert tokens.source == "device"
    assert stat.S_IMODE(store_path.stat().st_mode) == 0o600
    assert "refresh-initial" in store_path.read_text(encoding="utf-8")
    exchange = state["authorization_exchange"]
    assert isinstance(exchange, dict)
    assert exchange["grant_type"] == ["authorization_code"]
    assert exchange["code"] == ["authorization-123"]
    assert exchange["code_verifier"] == ["verifier-123"]


@pytest.mark.asyncio
async def test_import_codex_auth_copies_access_token_without_refresh_token(
    tmp_path: Path,
):
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    access_token = _jwt(expires_at=time.time() + 3600)
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": access_token,
                    "refresh_token": "must-not-be-copied",
                }
            }
        ),
        encoding="utf-8",
    )
    manager = CodexAuthManager(store_path=tmp_path / "project-auth.json")

    tokens = await manager.import_codex_auth(codex_home=codex_home)

    assert tokens.access_token == access_token
    assert tokens.refresh_token is None
    assert tokens.source == "codex_import"
    assert "must-not-be-copied" not in manager.store_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_imported_expired_token_requires_independent_login(tmp_path: Path):
    store_path = tmp_path / "auth.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "access_token": _jwt(expires_at=time.time() - 1),
                "refresh_token": None,
                "account_id": "account-123",
                "expires_at": time.time() - 1,
                "source": "codex_import",
            }
        ),
        encoding="utf-8",
    )
    manager = CodexAuthManager(store_path=store_path)

    with pytest.raises(CodexAuthError, match="independent session"):
        await manager.get_valid_tokens()


@pytest.mark.parametrize(
    ("expires_in", "refresh_token", "logged_in"),
    [
        (3600, None, True),
        (-1, "refresh-initial", True),
        (-1, None, False),
    ],
)
def test_status_reports_session_availability(
    tmp_path: Path,
    expires_in: float,
    refresh_token: str | None,
    logged_in: bool,
):
    expires_at = time.time() + expires_in
    store_path = tmp_path / "auth.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "access_token": _jwt(expires_at=expires_at),
                "refresh_token": refresh_token,
                "account_id": "account-123",
                "expires_at": expires_at,
                "source": "device",
            }
        ),
        encoding="utf-8",
    )

    status = CodexAuthManager(store_path=store_path).status()

    assert status.logged_in is logged_in


@pytest.mark.asyncio
async def test_device_login_replaces_valid_import_without_force(
    tmp_path: Path, codex_oauth_server
):
    endpoints, _ = codex_oauth_server
    store_path = tmp_path / "auth.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "access_token": _jwt(expires_at=time.time() + 3600),
                "refresh_token": None,
                "account_id": "account-123",
                "expires_at": time.time() + 3600,
                "source": "codex_import",
            }
        ),
        encoding="utf-8",
    )
    manager = CodexAuthManager(
        store_path=store_path,
        endpoints=endpoints,
        poll_interval=0.01,
        device_timeout=1,
    )

    tokens = await manager.login_device(lambda _url, _code: None)

    assert tokens.source == "device"
    assert tokens.refresh_token == "refresh-initial"


@pytest.mark.asyncio
async def test_concurrent_refresh_rotates_token_once(
    tmp_path: Path, codex_oauth_server
):
    endpoints, state = codex_oauth_server
    store_path = tmp_path / "auth.json"
    expired = CodexTokens(
        version=1,
        access_token=_jwt(expires_at=time.time() - 1),
        refresh_token="refresh-initial",
        account_id="account-123",
        expires_at=time.time() - 1,
        source="device",
    )
    store_path.write_text(
        json.dumps(
            {
                "version": expired.version,
                "access_token": expired.access_token,
                "refresh_token": expired.refresh_token,
                "account_id": expired.account_id,
                "expires_at": expired.expires_at,
                "source": expired.source,
            }
        ),
        encoding="utf-8",
    )
    first = CodexAuthManager(store_path=store_path, endpoints=endpoints)
    second = CodexAuthManager(store_path=store_path, endpoints=endpoints)

    first_result, second_result = await asyncio.gather(
        first.get_valid_tokens(),
        second.get_valid_tokens(),
    )

    assert state["refresh_count"] == 1
    assert first_result.access_token == second_result.access_token
    assert first_result.refresh_token == "refresh-rotated"


@pytest.mark.asyncio
async def test_invalid_refresh_requires_reauthentication(
    tmp_path: Path, codex_oauth_server
):
    endpoints, state = codex_oauth_server
    state["refresh_error"] = True
    store_path = tmp_path / "auth.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "access_token": _jwt(expires_at=time.time() - 1),
                "refresh_token": "refresh-reused",
                "account_id": "account-123",
                "expires_at": time.time() - 1,
                "source": "device",
            }
        ),
        encoding="utf-8",
    )
    manager = CodexAuthManager(store_path=store_path, endpoints=endpoints)

    with pytest.raises(CodexAuthError, match="auth login --force"):
        await manager.get_valid_tokens()


@pytest.mark.asyncio
async def test_logout_removes_only_local_auth_store(tmp_path: Path):
    store_path = tmp_path / "auth.json"
    store_path.write_text("{}", encoding="utf-8")
    manager = CodexAuthManager(store_path=store_path)

    assert await manager.logout() is True
    assert not store_path.exists()
    assert await manager.logout() is False
