import pytest
import pytest_asyncio
from httpx import AsyncClient


class TestMyResults:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/results/me")
        assert resp.status_code == 401

    async def test_returns_list_for_student(self, client: AsyncClient, token: str):
        resp = await client.get(
            "/api/v1/results/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "count" in body
        assert isinstance(body["data"], list)
        assert body["count"] == len(body["data"])

    async def test_returns_list_for_admin(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/results/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "data" in resp.json()

    async def test_no_completed_registrations_initially(self, client: AsyncClient, token: str):
        resp = await client.get(
            "/api/v1/results/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["data"] == []


class TestRegistrationResult:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/results/registrations/some-id")
        assert resp.status_code == 401

    async def test_not_found(self, client: AsyncClient, token: str):
        resp = await client.get(
            "/api/v1/results/registrations/nonexistent-reg-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["code"] == "REGISTRATION_NOT_FOUND"

    async def test_admin_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/results/registrations/nonexistent-reg-id",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


class TestExamLeaderboard:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/results/exams/exam-001")
        assert resp.status_code == 401

    async def test_student_forbidden(self, client: AsyncClient, token: str):
        resp = await client.get(
            "/api/v1/results/exams/exam-001",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_admin_can_access(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/results/exams/exam-001",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "exam_id" in body
        assert "data" in body
        assert "count" in body
        assert body["exam_id"] == "exam-001"

    async def test_exam_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/results/exams/nonexistent-exam",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["code"] == "EXAM_NOT_FOUND"

    async def test_leaderboard_empty_without_completed_registrations(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/results/exams/exam-001",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert isinstance(body["data"], list)

    async def test_leaderboard_response_has_exam_title(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/results/exams/exam-001",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "exam_title" in resp.json()
