import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ── Health ────────────────────────────────────────────────────────────────────

async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Auth ──────────────────────────────────────────────────────────────────────

async def test_token_success(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/token",
        json={"username": "demo", "password": "demo-password"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["token_type"] == "bearer"


async def test_token_wrong_password(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/token",
        json={"username": "demo", "password": "WRONG"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"


async def test_protected_without_token(client: AsyncClient):
    r = await client.post("/api/v1/exam-slots/slot-001/register")
    assert r.status_code == 401


# ── List API ──────────────────────────────────────────────────────────────────

async def test_list_exams_no_filter(client: AsyncClient):
    r = await client.get("/api/v1/exams")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "has_more" in body
    assert "next_cursor" in body
    assert len(body["data"]) > 0


async def test_list_exams_category_filter(client: AsyncClient):
    r = await client.get("/api/v1/exams?category=Mathematics")
    assert r.status_code == 200
    data = r.json()["data"]
    assert all("Math" in e["category"] for e in data)


async def test_list_exams_price_filter(client: AsyncClient):
    r = await client.get("/api/v1/exams?min_price=200&max_price=300")
    assert r.status_code == 200
    for e in r.json()["data"]:
        assert 200 <= e["fee"] <= 300


async def test_list_exams_status_filter(client: AsyncClient):
    r = await client.get("/api/v1/exams?status=scheduled")
    assert r.status_code == 200
    for e in r.json()["data"]:
        assert e["status"] == "scheduled"


async def test_list_exams_cursor_pagination(client: AsyncClient):
    r1 = await client.get("/api/v1/exams?limit=5")
    body1 = r1.json()
    assert body1["has_more"] is True
    cursor = body1["next_cursor"]
    assert isinstance(cursor, str)

    r2 = await client.get(f"/api/v1/exams?limit=5&after={cursor}")
    body2 = r2.json()
    assert isinstance(body2["data"], list)


async def test_get_exam_not_found(client: AsyncClient):
    r = await client.get("/api/v1/exams/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "EXAM_NOT_FOUND"


# ── Map API ───────────────────────────────────────────────────────────────────

async def test_nearby_centers(client: AsyncClient):
    r = await client.get(
        "/api/v1/exam-centers/nearby?latitude=28.6139&longitude=77.2090&radius_km=50"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    for c in body["data"]:
        assert "coordinates" in c
        assert c["distance_km"] <= 50


async def test_bbox_centers(client: AsyncClient):
    r = await client.get(
        "/api/v1/exam-centers/bbox?min_lat=18.0&min_lon=72.0&max_lat=29.0&max_lon=78.0"
    )
    assert r.status_code == 200
    assert r.json()["count"] >= 1


async def test_bbox_invalid_coords(client: AsyncClient):
    r = await client.get(
        "/api/v1/exam-centers/bbox?min_lat=30&min_lon=77&max_lat=20&max_lon=78"
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_COORDINATES"


# ── Calendar API ──────────────────────────────────────────────────────────────

async def test_list_slots_time_window(client: AsyncClient):
    r = await client.get(
        "/api/v1/exam-slots?starts_at=2027-03-01T00:00:00Z&ends_at=2027-03-31T23:59:59Z"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    for slot in body["data"]:
        assert slot["starts_at"] < "2027-04-01T00:00:00"


async def test_invalid_date_range(client: AsyncClient):
    r = await client.get(
        "/api/v1/exam-slots?starts_at=2027-06-01T00:00:00Z&ends_at=2027-01-01T00:00:00Z"
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_DATE_RANGE"


async def test_register_and_conflict(client: AsyncClient, token: str):
    headers = {"Authorization": f"Bearer {token}"}

    # First registration should succeed
    r1 = await client.post("/api/v1/exam-slots/slot-001/register", headers=headers)
    assert r1.status_code in (201, 409)  # 409 if already registered from a prior run

    # Second registration for same slot → ALREADY_REGISTERED
    r2 = await client.post("/api/v1/exam-slots/slot-001/register", headers=headers)
    assert r2.status_code == 409
    code = r2.json()["detail"]["code"]
    assert code in ("ALREADY_REGISTERED", "SLOT_CONFLICT")


async def test_slot_not_found(client: AsyncClient, token: str):
    r = await client.post(
        "/api/v1/exam-slots/nonexistent-slot/register",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SLOT_NOT_FOUND"


# ── GraphQL ───────────────────────────────────────────────────────────────────

async def test_graphql_list_exams(client: AsyncClient):
    query = """
    query {
      exams(first: 5) {
        edges { node { id title fee status } cursor }
        pageInfo { hasNextPage endCursor }
        totalCount
      }
    }
    """
    r = await client.post("/graphql", json={"query": query})
    assert r.status_code == 200
    body = r.json()
    assert "errors" not in body
    conn = body["data"]["exams"]
    assert len(conn["edges"]) > 0
    assert "hasNextPage" in conn["pageInfo"]


async def test_graphql_nearby_centers(client: AsyncClient):
    query = """
    query {
      nearbyExamCenters(latitude: 28.6139, longitude: 77.2090, radiusKm: 50) {
        id name distanceKm coordinates { longitude latitude }
      }
    }
    """
    r = await client.post("/graphql", json={"query": query})
    assert r.status_code == 200
    body = r.json()
    assert "errors" not in body
    centers = body["data"]["nearbyExamCenters"]
    assert len(centers) >= 1


async def test_graphql_authenticate(client: AsyncClient):
    query = """
    mutation {
      authenticate(username: "demo", password: "demo-password") {
        token tokenType expiresIn
      }
    }
    """
    r = await client.post("/graphql", json={"query": query})
    assert r.status_code == 200
    body = r.json()
    assert "errors" not in body
    assert body["data"]["authenticate"]["token"]
