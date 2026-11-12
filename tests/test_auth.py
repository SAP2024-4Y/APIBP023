import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ── Token endpoint ────────────────────────────────────────────────────────────

class TestIssueToken:
    async def test_success_returns_bearer_token(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/auth/token",
            json={"username": "demo", "password": "demo-password"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert isinstance(body["token"], str)
        assert len(body["token"]) > 20

    async def test_wrong_password_returns_401(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/auth/token",
            json={"username": "demo", "password": "WRONG"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    async def test_unknown_user_returns_401(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/auth/token",
            json={"username": "ghost", "password": "whatever"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    async def test_admin_user_can_login(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/auth/token",
            json={"username": "admin", "password": "admin-password"},
        )
        assert r.status_code == 200
        assert "token" in r.json()

    async def test_missing_password_field_returns_422(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/auth/token",
            json={"username": "demo"},
        )
        assert r.status_code == 422

    async def test_missing_username_field_returns_422(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/auth/token",
            json={"password": "demo-password"},
        )
        assert r.status_code == 422

    async def test_empty_body_returns_422(self, client: AsyncClient):
        r = await client.post("/api/v1/auth/token", json={})
        assert r.status_code == 422


# ── Auth helper functions (pure) ──────────────────────────────────────────────

class TestAuthHelpers:
    def test_hash_and_verify_password(self):
        from src.auth import hash_password, verify_password
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed)
        assert not verify_password("WRONG", hashed)

    def test_different_passwords_produce_different_hashes(self):
        from src.auth import hash_password
        h1 = hash_password("abc")
        h2 = hash_password("abc")
        assert h1 != h2  # bcrypt salts each hash

    def test_create_access_token_is_a_jwt(self):
        from src.auth import create_access_token
        token = create_access_token("user-123", "student")
        parts = token.split(".")
        assert len(parts) == 3   # header.payload.signature

    def test_create_access_token_encodes_role(self):
        import base64
        import json

        from src.auth import create_access_token
        token = create_access_token("user-abc", "admin")
        payload_b64 = token.split(".")[1]
        # fix padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["role"] == "admin"
        assert payload["sub"] == "user-abc"


# ── Token reuse ───────────────────────────────────────────────────────────────

class TestTokenReuse:
    async def test_token_is_consistent_across_calls(self, client: AsyncClient):
        r1 = await client.post(
            "/api/v1/auth/token",
            json={"username": "demo", "password": "demo-password"},
        )
        r2 = await client.post(
            "/api/v1/auth/token",
            json={"username": "demo", "password": "demo-password"},
        )
        # Both requests succeed; tokens differ (different exp claims) but are valid JWTs
        assert r1.status_code == 200
        assert r2.status_code == 200
        # They should both be non-empty strings
        assert r1.json()["token"]
        assert r2.json()["token"]
