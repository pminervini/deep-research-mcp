"""Tests for HTTP OAuth access-token verification."""

import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from deep_research_mcp.auth import AuthKitTokenVerifier, load_http_auth

RESOURCE_URL = "http://127.0.0.1:8080/mcp"
KEY_ID = "test-key"


@pytest.fixture
def authkit_signing_material(tmp_path):
    """Serve a real local JWKS endpoint and return its issuer and private key."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"alg": "RS256", "kid": KEY_ID, "use": "sig"})

    jwks_path = tmp_path / "oauth2" / "jwks"
    jwks_path.parent.mkdir()
    jwks_path.write_text(json.dumps({"keys": [public_jwk]}), encoding="utf-8")

    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", private_key
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _encode_token(private_key, issuer_url: str, **claim_overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer_url,
        "aud": RESOURCE_URL,
        "sub": "user_123",
        "client_id": "client_123",
        "scope": "openid profile",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(claim_overrides)
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )


def test_load_http_auth_is_opt_in():
    token_verifier, auth_settings = load_http_auth({})

    assert token_verifier is None
    assert auth_settings is None


def test_load_http_auth_requires_issuer_and_resource():
    with pytest.raises(ValueError, match="must be set together"):
        load_http_auth({"MCP_AUTH_ISSUER_URL": "https://example.authkit.app"})


def test_load_http_auth_configures_resource_server():
    token_verifier, auth_settings = load_http_auth(
        {
            "MCP_AUTH_ISSUER_URL": "https://example.authkit.app",
            "MCP_AUTH_RESOURCE_URL": RESOURCE_URL,
        }
    )

    assert isinstance(token_verifier, AuthKitTokenVerifier)
    assert auth_settings is not None
    assert str(auth_settings.issuer_url) == "https://example.authkit.app/"
    assert str(auth_settings.resource_server_url) == RESOURCE_URL
    assert not auth_settings.required_scopes


def test_authenticated_server_publishes_metadata_and_requires_bearer_token():
    token_verifier, auth_settings = load_http_auth(
        {
            "MCP_AUTH_ISSUER_URL": "https://example.authkit.app",
            "MCP_AUTH_RESOURCE_URL": RESOURCE_URL,
        }
    )
    server = FastMCP(
        "authenticated-test-server",
        token_verifier=token_verifier,
        auth=auth_settings,
    )

    with TestClient(server.streamable_http_app()) as client:
        metadata_response = client.get("/.well-known/oauth-protected-resource/mcp")
        protected_response = client.get("/mcp")

    assert metadata_response.status_code == 200
    assert metadata_response.json()["resource"] == RESOURCE_URL
    assert metadata_response.json()["authorization_servers"] == [
        "https://example.authkit.app/"
    ]
    assert protected_response.status_code == 401
    assert "resource_metadata=" in protected_response.headers["WWW-Authenticate"]


@pytest.mark.asyncio
async def test_verifier_accepts_valid_authkit_token(authkit_signing_material):
    issuer_url, private_key = authkit_signing_material
    verifier = AuthKitTokenVerifier(issuer_url, RESOURCE_URL)

    access_token = await verifier.verify_token(_encode_token(private_key, issuer_url))

    assert access_token is not None
    assert access_token.client_id == "client_123"
    assert access_token.subject == "user_123"
    assert access_token.scopes == ["openid", "profile"]
    assert access_token.resource == RESOURCE_URL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"aud": "https://wrong.example/mcp"},
        {"iss": "https://wrong.example"},
        {"exp": 0},
    ],
)
async def test_verifier_rejects_invalid_authkit_token(
    authkit_signing_material, claim_overrides
):
    issuer_url, private_key = authkit_signing_material
    verifier = AuthKitTokenVerifier(issuer_url, RESOURCE_URL)
    token = _encode_token(private_key, issuer_url, **claim_overrides)

    assert await verifier.verify_token(token) is None
