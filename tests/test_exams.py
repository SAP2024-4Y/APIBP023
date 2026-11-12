"""
Integration tests for src/routers/exams.py — List API.

Covers:
  - GET /api/v1/exams             — no filter, returns paginated list
  - GET /api/v1/exams?category=   — category filter
  - GET /api/v1/exams?status=     — status filter
  - GET /api/v1/exams?min_price=  — price range filter
  - GET /api/v1/exams?sort=&order=— sorting
  - GET /api/v1/exams?limit=      — page size
  - GET /api/v1/exams?after=      — cursor pagination
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestListExams:
    async def test_returns_200_with_data(self, client: AsyncClient):
        r = await client.get("/api/v1/exams")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) > 0

    async def test_response_has_pagination_fields(self, client: AsyncClient):
        r = await client.get("/api/v1/exams")
        body = r.json()
        assert "has_more" in body
        assert "next_cursor" in body

    async def test_each_item_has_required_fields(self, client: AsyncClient):
        r = await client.get("/api/v1/exams")
        for exam in r.json()["data"]:
            assert "id" in exam
            assert "title" in exam
            assert "fee" in exam
            assert "status" in exam

    async def test_category_filter_mathematics(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?category=Mathematics")
        assert r.status_code == 200
        for exam in r.json()["data"]:
            assert "Math" in exam["category"]

    async def test_status_filter_scheduled(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?status=scheduled")
        assert r.status_code == 200
        for exam in r.json()["data"]:
            assert exam["status"] == "scheduled"

    async def test_price_range_filter(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?min_price=100&max_price=400")
        assert r.status_code == 200
        for exam in r.json()["data"]:
            assert 100 <= exam["fee"] <= 400

    async def test_min_price_only(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?min_price=300")
        assert r.status_code == 200
        for exam in r.json()["data"]:
            assert exam["fee"] >= 300

    async def test_max_price_only(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?max_price=200")
        assert r.status_code == 200
        for exam in r.json()["data"]:
            assert exam["fee"] <= 200

    async def test_limit_param(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?limit=3")
        assert r.status_code == 200
        assert len(r.json()["data"]) <= 3

    async def test_cursor_pagination(self, client: AsyncClient):
        r1 = await client.get("/api/v1/exams?limit=3")
        body1 = r1.json()
        if not body1["has_more"]:
            pytest.skip("Not enough seed data for pagination test")
        cursor = body1["next_cursor"]
        r2 = await client.get(f"/api/v1/exams?limit=3&after={cursor}")
        assert r2.status_code == 200
        # Second page must be a valid list
        assert isinstance(r2.json()["data"], list)
        # Cursor itself must be a non-empty string
        assert isinstance(cursor, str) and len(cursor) > 0

    async def test_sort_by_fee_asc(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?sort=fee&order=asc&limit=20")
        assert r.status_code == 200
        fees = [e["fee"] for e in r.json()["data"]]
        assert fees == sorted(fees)

    async def test_sort_by_fee_desc(self, client: AsyncClient):
        r = await client.get("/api/v1/exams?sort=fee&order=desc&limit=20")
        assert r.status_code == 200
        fees = [e["fee"] for e in r.json()["data"]]
        assert fees == sorted(fees, reverse=True)

    async def test_combined_filters(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/exams?category=Mathematics&min_price=0&max_price=500&sort=fee&order=asc&limit=5"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        for exam in data:
            assert "Math" in exam["category"]
            assert exam["fee"] <= 500
