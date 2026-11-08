"""
Map API — exam-center geospatial endpoints

GET /api/v1/exam-centers          – list all centers
GET /api/v1/exam-centers/nearby   – proximity search (latitude, longitude, radius_km)
GET /api/v1/exam-centers/bbox     – bounding-box search (min_lat, min_lon, max_lat, max_lon)
GET /api/v1/exam-centers/{id}     – single center

GeoJSON convention: position = [longitude, latitude]
"""
from math import asin, cos, radians, sin, sqrt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models import ExamCenter

router = APIRouter(prefix="/exam-centers", tags=["exam-centers"])


# ---------------------------------------------------------------------------
# Haversine distance (km)
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371.0
    φ1, λ1, φ2, λ2 = map(radians, [lat1, lon1, lat2, lon2])
    dφ = φ2 - φ1
    dλ = λ2 - λ1
    a = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    return R * 2 * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Serialiser — GeoJSON position [lon, lat]
# ---------------------------------------------------------------------------

def _center_out(c: ExamCenter, distance_km: Optional[float] = None) -> dict:
    out = {
        "id": c.id,
        "name": c.name,
        "address": c.address,
        "city": c.city,
        "state": c.state,
        "capacity": c.capacity,
        "contact_email": c.contact_email,
        # GeoJSON: [longitude, latitude]
        "coordinates": [c.longitude, c.latitude],
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    if distance_km is not None:
        out["distance_km"] = round(distance_km, 3)
    return out


# ---------------------------------------------------------------------------
# Routes — order matters: /nearby and /bbox BEFORE /{id}
# ---------------------------------------------------------------------------

@router.get("/nearby", summary="Find exam centers within radius_km of a point")
@limiter.limit("100/minute")
async def nearby_centers(
    request: Request,
    latitude: float = Query(..., ge=-90, le=90, description="Decimal degrees"),
    longitude: float = Query(..., ge=-180, le=180, description="Decimal degrees"),
    radius_km: float = Query(50.0, gt=0, description="Search radius in kilometres"),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(ExamCenter))).scalars().all()
    results = []
    for c in rows:
        dist = _haversine(latitude, longitude, c.latitude, c.longitude)
        if dist <= radius_km:
            results.append(_center_out(c, dist))
    results.sort(key=lambda x: x["distance_km"])
    return {"data": results, "count": len(results)}


@router.get("/bbox", summary="Find exam centers inside a bounding box")
@limiter.limit("100/minute")
async def bbox_centers(
    request: Request,
    min_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
    max_lon: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_COORDINATES", "message": "min_lat/min_lon must be less than max_lat/max_lon"},
        )
    rows = (
        await db.execute(
            select(ExamCenter).where(
                ExamCenter.latitude >= min_lat,
                ExamCenter.latitude <= max_lat,
                ExamCenter.longitude >= min_lon,
                ExamCenter.longitude <= max_lon,
            )
        )
    ).scalars().all()
    return {"data": [_center_out(c) for c in rows], "count": len(rows)}


@router.get("", summary="List all exam centers")
@limiter.limit("100/minute")
async def list_centers(request: Request, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ExamCenter))).scalars().all()
    return {"data": [_center_out(c) for c in rows], "count": len(rows)}


@router.get("/{center_id}", summary="Get a single exam center by ID")
@limiter.limit("100/minute")
async def get_center(request: Request, center_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExamCenter).where(ExamCenter.id == center_id))
    center = result.scalar_one_or_none()
    if not center:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CENTER_NOT_FOUND", "message": f"Exam center '{center_id}' not found"},
        )
    return _center_out(center)
