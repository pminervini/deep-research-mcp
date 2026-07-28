"""OAuth access-token verification for the HTTP MCP transport."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

logger = logging.getLogger(__name__)

AUTH_ISSUER_ENV = "MCP_AUTH_ISSUER_URL"
AUTH_RESOURCE_ENV = "MCP_AUTH_RESOURCE_URL"


class AuthKitTokenVerifier(TokenVerifier):
    """Verify AuthKit JWT access tokens using its published JWKS."""

    def __init__(self, issuer_url: str, resource_url: str) -> None:
        self.issuer_url = issuer_url.rstrip("/")
        self.resource_url = resource_url
        self._jwks_client = PyJWKClient(f"{self.issuer_url}/oauth2/jwks")

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = await asyncio.to_thread(
                self._jwks_client.get_signing_key_from_jwt, token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.resource_url,
                issuer=self.issuer_url,
                options={"require": ["aud", "exp", "iss", "sub"]},
            )
        except (PyJWTError, OSError, ValueError) as error:
            logger.debug(f"Rejected OAuth access token: {type(error).__name__}")
            return None

        subject = str(claims["sub"])
        client_id = str(claims.get("client_id") or claims.get("azp") or subject)
        scope_claim = claims.get("scope", "")
        scopes = scope_claim.split() if isinstance(scope_claim, str) else []

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=self.resource_url,
            subject=subject,
            claims=claims,
        )


def load_http_auth(
    env: Mapping[str, str] | None = None,
) -> tuple[TokenVerifier | None, AuthSettings | None]:
    """Load optional HTTP OAuth configuration from the environment."""
    settings = os.environ if env is None else env
    issuer_url = settings.get(AUTH_ISSUER_ENV)
    resource_url = settings.get(AUTH_RESOURCE_ENV)

    if not issuer_url and not resource_url:
        return None, None
    if not issuer_url or not resource_url:
        raise ValueError(
            f"{AUTH_ISSUER_ENV} and {AUTH_RESOURCE_ENV} must be set together"
        )

    token_verifier = AuthKitTokenVerifier(issuer_url, resource_url)
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        resource_server_url=AnyHttpUrl(resource_url),
        required_scopes=[],
    )
    return token_verifier, auth_settings
