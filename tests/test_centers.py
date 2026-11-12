import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# New Delhi coordinates — seed data centers are around this area
DELHI_LAT = 28.6139
DELHI_LON = 77.2090


class TestListCenters:
    async def test_returns_all_centers(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-centers")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert len(body["data"]) > 0

    async def test_each_center_has_coordinates(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-centers")
        for c in r.json()["data"]:
            assert "coordinates" in c
            coords = c["coordinates"]
            assert isinstance(coords, list)
            assert len(coords) == 2   # [longitude, latitude]

    async def test_single_center_by_id(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-centers")
        first_id = r.json()["data"][0]["id"]
        r2 = await client.get(f"/api/v1/exam-centers/{first_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == first_id

    async def test_single_center_not_found(self, client: AsyncClient):
        r = await client.get("/api/v1/exam-centers/nonexistent-id")
        assert r.status_code == 404


class TestNearbyCenters:
    async def test_nearby_returns_200(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/exam-centers/nearby"
            f"?latitude={DELHI_LAT}&longitude={DELHI_LON}&radius_km=500"
        )
        assert r.status_code == 200

    async def test_nearby_has_distance_field(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/exam-centers/nearby"
            f"?latitude={DELHI_LAT}&longitude={DELHI_LON}&radius_km=500"
        )
        for c in r.json()["data"]:
            assert "distance_km" in c
            assert c["distance_km"] >= 0

    async def test_nearby_results_within_radius(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/exam-centers/nearby"
            f"?latitude={DELHI_LAT}&longitude={DELHI_LON}&radius_km=100"
        )
        assert r.status_code == 200
        for c in r.json()["data"]:
            assert c["distance_km"] <= 100

    async def test_nearby_sorted_by_distance(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/exam-centers/nearby"
            f"?latitude={DELHI_LAT}&longitude={DELHI_LON}&radius_km=500"
        )
        distances = [c["distance_km"] for c in r.json()["data"]]
        assert distances == sorted(distances)

    async def test_nearby_very_small_radius_returns_empty_or_few(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/exam-centers/nearby"
            "?latitude=0.0&longitude=0.0&radius_km=1"
        )
        assert r.status_code == 200
        assert len(r.json()["data"]) == 0

    async def test_nearby_missing_lat_returns_422(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/exam-centers/nearby?longitude={DELHI_LON}&radius_km=50"
        )
        assert r.status_code == 422

    async def test_nearby_missing_lon_returns_422(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/exam-centers/nearby?latitude={DELHI_LAT}&radius_km=50"
        )
        assert r.status_code == 422


class TestBboxCenters:
    async def test_bbox_returns_200(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/exam-centers/bbox"
            "?min_lat=28.0&min_lon=76.0&max_lat=29.5&max_lon=78.0"
        )
        assert r.status_code == 200

    async def test_bbox_centers_within_bounds(self, client: AsyncClient):
        min_lat, min_lon, max_lat, max_lon = 28.0, 76.0, 29.5, 78.0
        r = await client.get(
            f"/api/v1/exam-centers/bbox"
            f"?min_lat={min_lat}&min_lon={min_lon}&max_lat={max_lat}&max_lon={max_lon}"
        )
        for c in r.json()["data"]:
            lon, lat = c["coordinates"]   # GeoJSON: [lon, lat]
            assert min_lat <= lat <= max_lat
            assert min_lon <= lon <= max_lon

    async def test_bbox_empty_area_returns_empty(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/exam-centers/bbox"
            "?min_lat=0.0&min_lon=0.0&max_lat=1.0&max_lon=1.0"
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    async def test_bbox_missing_param_returns_422(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/exam-centers/bbox?min_lat=28.0&min_lon=76.0&max_lat=29.5"
        )
        assert r.status_code == 422


class TestHaversine:
    def test_same_point_is_zero(self):
        from src.routers.centers import _haversine
        assert _haversine(28.6, 77.2, 28.6, 77.2) == 0.0

    def test_delhi_to_mumbai_approx(self):
        from src.routers.centers import _haversine
        dist = _haversine(28.6139, 77.2090, 19.0760, 72.8777)
        assert 1100 < dist < 1600, f"Expected ~1400 km, got {dist:.1f}"

    def test_symmetry(self):
        from src.routers.centers import _haversine
        d1 = _haversine(28.6, 77.2, 19.1, 72.9)
        d2 = _haversine(19.1, 72.9, 28.6, 77.2)
        assert abs(d1 - d2) < 0.001
