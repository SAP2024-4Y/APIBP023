"""
Integration tests for src/routers/slots.py and src/routers/registrations.py — Calendar API.

Covers:
  - GET  /api/v1/exam-slots                 — list by time window
  - GET  /api/v1/exam-slots/{id}            — single slot
  - POST /api/v1/exam-slots/{id}/register   — register (auth required)
  - 409  on slot conflict
  - DELETE /api/v1/exam-slots/{id}/register — cancel registration
  - GET  /api/v1/registrations              — student's own registrations
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestListSlots:
    async def test_list_no_filter_returns_all(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-slots")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert len(body["data"]) > 0

    async def test_each_slot_has_required_fields(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-slots")
        for slot in r.json()["data"]:
            assert "id" in slot
            assert "exam_id" in slot
            assert "starts_at" in slot
            assert "ends_at" in slot
            assert "available_seats" in slot

    async def test_time_window_filter(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/exam-slots"
            "?starts_at=2027-01-01T00:00:00Z&ends_at=2027-06-30T23:59:59Z"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        for slot in data:
            assert slot["starts_at"] >= "2027-01-01"
            assert slot["ends_at"] <= "2027-07-01"

    async def test_future_window_only_returns_relevant_slots(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/exam-slots"
            "?starts_at=2030-01-01T00:00:00Z&ends_at=2030-12-31T23:59:59Z"
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    async def test_single_slot_by_id(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-slots")
        first_id = r.json()["data"][0]["id"]
        r2 = await client.get(f"/api/v1/exam-slots/{first_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == first_id

    async def test_single_slot_not_found(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-slots/nonexistent-slot")
        assert r.status_code == 404


class TestRegistration:
    async def test_register_requires_auth(self, client: AsyncClient):
        r = await client.post("/api/v1/exam-slots/slot-001/register")
        assert r.status_code == 401

    async def test_register_student_creates_registration(self, client: AsyncClient, token: str):
        r = await client.post(
            "/api/v1/exam-slots/slot-001/register",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code in (201, 409)   # 409 if already registered from a prior run
        if r.status_code == 201:
            body = r.json()
            assert "id" in body
            assert body["slot_id"] == "slot-001"

    async def test_double_register_same_slot_is_409(self, client: AsyncClient, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        r1 = await client.post("/api/v1/exam-slots/slot-001/register", headers=headers)
        r2 = await client.post("/api/v1/exam-slots/slot-001/register", headers=headers)
        # At least the second call must be 409
        assert r2.status_code == 409

    async def test_cancel_registration(self, client: AsyncClient, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        # Ensure registered first
        await client.post("/api/v1/exam-slots/slot-002/register", headers=headers)
        r = await client.delete(
            "/api/v1/exam-slots/slot-002/register",
            headers=headers,
        )
        assert r.status_code in (200, 204, 404)   # 200/204 on success, 404 if not registered

    async def test_cancel_nonexistent_slot_returns_404(self, client: AsyncClient, token: str):
        r = await client.delete(
            "/api/v1/exam-slots/nonexistent-slot/register",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    async def test_cancel_requires_auth(self, client: AsyncClient):
        r = await client.delete("/api/v1/exam-slots/slot-001/register")
        assert r.status_code == 401


class TestRegistrationsList:
    async def test_list_own_registrations(self, client: AsyncClient, token: str):
        # Register first so there's at least one entry
        await client.post(
            "/api/v1/exam-slots/slot-001/register",
            headers={"Authorization": f"Bearer {token}"},
        )
        r = await client.get(
            "/api/v1/registrations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "data" in body

    async def test_registrations_requires_auth(self, client: AsyncClient):
        r = await client.get("/api/v1/registrations")
        assert r.status_code == 401
