# -*- coding: utf-8 -*-

"""OpenAI Codex subscription OAuth and local credential storage."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from filelock import AsyncFileLock
import httpx

from deep_research_mcp.errors import ResearchError

CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_CODEX_AUTH_PATH = Path.home() / ".deep_research_auth.json"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
REFRESH_SKEW_SECONDS = 120.0


class CodexAuthError(ResearchError):
    """OpenAI Codex subscription authentication failed."""


@dataclass(frozen=True, slots=True)
class CodexAuthEndpoints:
    """OAuth endpoints used by the Codex device flow."""

    user_code_url: str = "https://auth.openai.com/api/accounts/deviceauth/usercode"
    device_token_url: str = "https://auth.openai.com/api/accounts/deviceauth/token"
    oauth_token_url: str = "https://auth.openai.com/oauth/token"
    verification_url: str = "https://auth.openai.com/codex/device"
    redirect_uri: str = "https://auth.openai.com/deviceauth/callback"


@dataclass(frozen=True, slots=True)
class CodexTokens:
    """Credentials required by the ChatGPT Codex backend."""

    version: int
    access_token: str
    refresh_token: str | None
    account_id: str
    expires_at: float
    source: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodexTokens":
        """Validate and normalize a stored credential record."""
        try:
            version = int(data["version"])
            access_token = data["access_token"]
            account_id = data["account_id"]
            expires_at = float(data["expires_at"])
            source = data["source"]
        except (KeyError, TypeError, ValueError) as error:
            raise CodexAuthError(
                "Stored OpenAI Codex credentials are invalid; run `auth login --force`"
            ) from error
        string_fields = (access_token, account_id, source)
        if version != 1 or any(
            not isinstance(value, str) or not value for value in string_fields
        ):
            raise CodexAuthError(
                "Stored OpenAI Codex credentials are invalid; run `auth login --force`"
            )
        refresh_token = data.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise CodexAuthError(
                "Stored OpenAI Codex credentials are invalid; run `auth login --force`"
            )
        return cls(
            version=version,
            access_token=access_token,
            refresh_token=refresh_token or None,
            account_id=account_id,
            expires_at=expires_at,
            source=source,
        )


@dataclass(frozen=True, slots=True)
class CodexAuthStatus:
    """Safe, user-facing credential status."""

    logged_in: bool
    source: str | None = None
    expires_at: float | None = None
    message: str | None = None


class CodexAuthManager:
    """Manage an independent OpenAI Codex OAuth session."""

    def __init__(
        self,
        *,
        store_path: Path | None = None,
        endpoints: CodexAuthEndpoints | None = None,
        poll_interval: float = 5.0,
        device_timeout: float = 900.0,
        refresh_skew: float = REFRESH_SKEW_SECONDS,
    ) -> None:
        self.store_path = store_path or DEFAULT_CODEX_AUTH_PATH
        self.endpoints = endpoints or CodexAuthEndpoints()
        self.poll_interval = poll_interval
        self.device_timeout = device_timeout
        self.refresh_skew = refresh_skew
        self._lock_path = f"{self.store_path}.lock"

    def status(self, *, now: float | None = None) -> CodexAuthStatus:
        """Return credential state without refreshing or exposing secrets."""
        current_time = time.time() if now is None else now
        if not self.store_path.exists():
            return CodexAuthStatus(
                logged_in=False,
                message="No OpenAI Codex credentials stored",
            )

        try:
            tokens = self._read_tokens()
        except CodexAuthError as error:
            return CodexAuthStatus(logged_in=False, message=str(error))

        expired = tokens.expires_at <= current_time
        return CodexAuthStatus(
            logged_in=not expired or bool(tokens.refresh_token),
            source=tokens.source,
            expires_at=tokens.expires_at,
            message=(
                "Imported Codex credentials expired; run `auth login`"
                if expired and not tokens.refresh_token
                else (
                    "Access token will refresh on next use"
                    if expired and tokens.refresh_token
                    else None
                )
            ),
        )

    async def login_device(
        self,
        display_code: Callable[[str, str], None],
        *,
        force: bool = False,
    ) -> CodexTokens:
        """Authenticate with OpenAI's Codex device-code flow."""
        existing = self._read_tokens_if_present()
        if (
            existing
            and existing.source == "device"
            and existing.expires_at > time.time() + self.refresh_skew
            and not force
        ):
            return existing

        async with httpx.AsyncClient(timeout=30.0) as client:
            user_code_response = await client.post(
                self.endpoints.user_code_url,
                json={"client_id": CODEX_OAUTH_CLIENT_ID},
            )
            self._raise_oauth_error(user_code_response, "start device login")
            user_code_data = self._json_object(user_code_response)

            device_auth_id = self._required_string(user_code_data, "device_auth_id")
            user_code = self._required_string(user_code_data, "user_code")
            display_code(self.endpoints.verification_url, user_code)

            device_token = await self._poll_device_token(
                client,
                device_auth_id=device_auth_id,
                user_code=user_code,
            )
            authorization_code = self._required_string(
                device_token, "authorization_code"
            )
            code_verifier = self._required_string(device_token, "code_verifier")

            token_response = await client.post(
                self.endpoints.oauth_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": authorization_code,
                    "redirect_uri": self.endpoints.redirect_uri,
                    "client_id": CODEX_OAUTH_CLIENT_ID,
                    "code_verifier": code_verifier,
                },
            )
            self._raise_oauth_error(token_response, "exchange device authorization")
            tokens = self._tokens_from_oauth_response(
                self._json_object(token_response),
                source="device",
            )

        await self._write_tokens_locked(tokens)
        return tokens

    async def import_codex_auth(
        self,
        *,
        codex_home: Path | None = None,
        force: bool = False,
    ) -> CodexTokens:
        """Copy a current Codex access token without sharing its refresh token."""
        existing = self._read_tokens_if_present()
        if (
            existing
            and existing.expires_at > time.time() + self.refresh_skew
            and not force
        ):
            return existing

        auth_path = (codex_home or DEFAULT_CODEX_HOME).expanduser() / "auth.json"
        if not auth_path.exists():
            raise CodexAuthError(
                f"Codex credentials were not found at {auth_path}; run `auth login`"
            )

        try:
            data = json.loads(auth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CodexAuthError(
                f"Could not read Codex credentials from {auth_path}"
            ) from error

        token_data = data.get("tokens") if isinstance(data, dict) else None
        if not isinstance(token_data, dict):
            raise CodexAuthError(
                f"Codex credentials at {auth_path} do not contain tokens"
            )

        access_token = self._required_string(token_data, "access_token")
        id_token = token_data.get("id_token")
        account_id = token_data.get("account_id")
        if not account_id and id_token:
            account_id = _account_id_from_jwt(str(id_token))
        if not account_id:
            account_id = _account_id_from_jwt(access_token)
        if not account_id:
            raise CodexAuthError(
                "Could not determine the ChatGPT account ID from Codex credentials"
            )

        expires_at = _expiry_from_jwt(access_token)
        if expires_at is None:
            raise CodexAuthError(
                "Could not determine when the imported Codex access token expires"
            )
        if expires_at <= time.time():
            raise CodexAuthError(
                "Codex access token is expired; run `auth login` for an independent session"
            )

        tokens = CodexTokens(
            version=1,
            access_token=access_token,
            refresh_token=None,
            account_id=str(account_id),
            expires_at=expires_at,
            source="codex_import",
        )
        await self._write_tokens_locked(tokens)
        return tokens

    async def logout(self) -> bool:
        """Delete this project's local Codex credentials."""
        async with AsyncFileLock(self._lock_path, timeout=10):
            if not self.store_path.exists():
                return False
            self.store_path.unlink()
            return True

    async def get_valid_tokens(self, *, force_refresh: bool = False) -> CodexTokens:
        """Load credentials, refreshing an independent device session if needed."""
        tokens = self._read_tokens_if_present()
        if not tokens:
            raise CodexAuthError(
                "OpenAI Codex is not authenticated; run `auth login` "
                "or `auth login --import-codex`"
            )

        if not force_refresh and tokens.expires_at > time.time() + self.refresh_skew:
            return tokens
        if not tokens.refresh_token:
            raise CodexAuthError(
                "Imported Codex credentials expired or were rejected; "
                "run `auth login` for an independent session"
            )

        return await self._refresh_tokens(tokens, force=force_refresh)

    async def _refresh_tokens(
        self, previous: CodexTokens, *, force: bool
    ) -> CodexTokens:
        async with AsyncFileLock(self._lock_path, timeout=10):
            current = self._read_tokens()
            if (
                current.access_token != previous.access_token
                and current.expires_at > time.time() + self.refresh_skew
            ):
                return current
            if not force and current.expires_at > time.time() + self.refresh_skew:
                return current
            if not current.refresh_token:
                raise CodexAuthError(
                    "OpenAI Codex credentials cannot be refreshed; run `auth login`"
                )

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.endpoints.oauth_token_url,
                    json={
                        "client_id": CODEX_OAUTH_CLIENT_ID,
                        "grant_type": "refresh_token",
                        "refresh_token": current.refresh_token,
                    },
                )
            if response.is_error:
                detail = _response_error_detail(response)
                raise CodexAuthError(
                    "OpenAI Codex token refresh failed"
                    f"{f': {detail}' if detail else ''}; run `auth login --force`"
                )

            refreshed = self._tokens_from_oauth_response(
                self._json_object(response),
                source=current.source,
                fallback_refresh_token=current.refresh_token,
            )
            self._write_tokens(refreshed)
            return refreshed

    async def _poll_device_token(
        self,
        client: httpx.AsyncClient,
        *,
        device_auth_id: str,
        user_code: str,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.device_timeout
        while time.monotonic() < deadline:
            response = await client.post(
                self.endpoints.device_token_url,
                json={
                    "device_auth_id": device_auth_id,
                    "user_code": user_code,
                },
            )
            if response.status_code in {403, 404}:
                await asyncio.sleep(self.poll_interval)
                continue
            self._raise_oauth_error(response, "complete device login")
            return self._json_object(response)

        raise CodexAuthError("OpenAI Codex device login timed out")

    def _tokens_from_oauth_response(
        self,
        data: dict[str, Any],
        *,
        source: str,
        fallback_refresh_token: str | None = None,
    ) -> CodexTokens:
        access_token = self._required_string(data, "access_token")
        refresh_token = data.get("refresh_token") or fallback_refresh_token
        account_id = (
            data.get("account_id")
            or _account_id_from_jwt(str(data.get("id_token", "")))
            or _account_id_from_jwt(access_token)
        )
        if not account_id:
            raise CodexAuthError(
                "OpenAI OAuth response did not identify a ChatGPT account"
            )

        expires_at = _expiry_from_jwt(access_token)
        if expires_at is None:
            try:
                expires_at = time.time() + float(data["expires_in"])
            except (KeyError, TypeError, ValueError) as error:
                raise CodexAuthError(
                    "OpenAI OAuth response did not include token expiry"
                ) from error

        return CodexTokens(
            version=1,
            access_token=access_token,
            refresh_token=str(refresh_token) if refresh_token else None,
            account_id=str(account_id),
            expires_at=expires_at,
            source=source,
        )

    async def _write_tokens_locked(self, tokens: CodexTokens) -> None:
        async with AsyncFileLock(self._lock_path, timeout=10):
            self._write_tokens(tokens)

    def _read_tokens_if_present(self) -> CodexTokens | None:
        if not self.store_path.exists():
            return None
        return self._read_tokens()

    def _read_tokens(self) -> CodexTokens:
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CodexAuthError(
                "OpenAI Codex credentials are not stored; run `auth login`"
            ) from error
        except (OSError, json.JSONDecodeError) as error:
            raise CodexAuthError(
                "Could not read stored OpenAI Codex credentials"
            ) from error
        if not isinstance(data, dict):
            raise CodexAuthError("Stored OpenAI Codex credentials are invalid")
        return CodexTokens.from_dict(data)

    def _write_tokens(self, tokens: CodexTokens) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{self.store_path.name}.",
            dir=self.store_path.parent,
        )
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(file_descriptor, 0o600)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as auth_file:
                json.dump(asdict(tokens), auth_file, separators=(",", ":"))
                auth_file.write("\n")
                auth_file.flush()
                os.fsync(auth_file.fileno())
            os.replace(temporary_path, self.store_path)
            self.store_path.chmod(0o600)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _required_string(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise CodexAuthError(f"OpenAI OAuth response is missing `{key}`")
        return value

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except json.JSONDecodeError as error:
            raise CodexAuthError("OpenAI OAuth returned invalid JSON") from error
        if not isinstance(data, dict):
            raise CodexAuthError("OpenAI OAuth returned an invalid response")
        return data

    @staticmethod
    def _raise_oauth_error(response: httpx.Response, action: str) -> None:
        if not response.is_error:
            return
        detail = _response_error_detail(response)
        raise CodexAuthError(
            f"Could not {action}"
            f"{f': {detail}' if detail else ''} "
            f"(HTTP {response.status_code})"
        )


def _jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        padding = "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(f"{parts[1]}{padding}")
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _expiry_from_jwt(token: str) -> float | None:
    payload = _jwt_payload(token)
    if not payload:
        return None
    try:
        return float(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return None


def _account_id_from_jwt(token: str) -> str | None:
    payload = _jwt_payload(token)
    if not payload:
        return None

    direct = payload.get("chatgpt_account_id") or payload.get(
        "https://api.openai.com/auth.chatgpt_account_id"
    )
    if direct:
        return str(direct)

    auth_claim = payload.get("https://api.openai.com/auth")
    if isinstance(auth_claim, dict) and auth_claim.get("chatgpt_account_id"):
        return str(auth_claim["chatgpt_account_id"])
    return None


def _response_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return response.text.strip()[:300]
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "")
    return str(error or data.get("message") or "")
