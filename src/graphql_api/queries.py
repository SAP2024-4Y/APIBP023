"""GraphQL queries (read-only operations)."""
import base64
import json
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Exam, ExamCenter, ExamSlot, Registration
from .types import (
    CoordinatesType,
    ExamCenterType,
    ExamConnection,
    ExamEdge,
    ExamSlotType,
    ExamType,
    PageInfo,
    RegistrationType,
)

_SORTABLE = {"created_at", "fee", "title", "subject", "duration_minutes", "total_marks"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_cursor(exam_id: str, ts: datetime) -> str:
    return base64.urlsafe_b64encode(
        json.dumps({"id": exam_id, "ts": ts.isoformat()}).encode()
    ).decode()


def _decode_cursor(cursor: str):
    try:
        d = json.loads(base64.urlsafe_b64decode(cursor).decode())
        return d["id"], datetime.fromisoformat(d["ts"])
    except Exception:
        return None, None


def _exam_node(e: Exam) -> ExamType:
    return ExamType(
        id=e.id,
        title=e.title,
        category=e.subject,
        description=e.description,
        duration_minutes=e.duration_minutes,
        total_marks=e.total_marks,
        passing_marks=e.passing_marks,
        fee=e.fee,
        status=e.status,
        created_at=e.created_at,
    )


def _center_node(c: ExamCenter, distance_km: Optional[float] = None) -> ExamCenterType:
    return ExamCenterType(
        id=c.id,
        name=c.name,
        address=c.address,
        city=c.city,
        state=c.state,
        capacity=c.capacity,
        contact_email=c.contact_email,
        coordinates=CoordinatesType(longitude=c.longitude, latitude=c.latitude),
        distance_km=distance_km,
    )


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371.0
    φ1, λ1, φ2, λ2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((φ2 - φ1) / 2) ** 2 + cos(φ1) * cos(φ2) * sin((λ2 - λ1) / 2) ** 2
    return R * 2 * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Query resolvers
# ---------------------------------------------------------------------------

async def resolve_exams(
    db: AsyncSession,
    first: int = 20,
    after: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "created_at",
    order: str = "desc",
) -> ExamConnection:
    if sort not in _SORTABLE:
        sort = "created_at"
    first = max(1, min(first, 100))

    conditions = []
    if status:
        conditions.append(Exam.status == status)
    if category:
        conditions.append(Exam.subject.ilike(f"%{category}%"))
    if min_price is not None:
        conditions.append(Exam.fee >= min_price)
    if max_price is not None:
        conditions.append(Exam.fee <= max_price)

    if after:
        cid, cts = _decode_cursor(after)
        if cts:
            if order == "desc":
                conditions.append(
                    or_(Exam.created_at < cts, and_(Exam.created_at == cts, Exam.id < cid))
                )
            else:
                conditions.append(
                    or_(Exam.created_at > cts, and_(Exam.created_at == cts, Exam.id > cid))
                )

    q = select(Exam)
    if conditions:
        q = q.where(and_(*conditions))

    sort_col = getattr(Exam, sort)
    q = q.order_by(
        sort_col.desc() if order == "desc" else sort_col.asc(),
        Exam.id.desc() if order == "desc" else Exam.id.asc(),
    ).limit(first + 1)

    rows = (await db.execute(q)).scalars().all()
    has_next = len(rows) > first
    rows = rows[:first]

    edges = [ExamEdge(node=_exam_node(e), cursor=_encode_cursor(e.id, e.created_at)) for e in rows]
    end_cursor = edges[-1].cursor if edges else None

    # total count (without cursor/limit)
    count_q = select(Exam)
    total = len((await db.execute(count_q)).scalars().all())

    return ExamConnection(
        edges=edges,
        page_info=PageInfo(
            has_next_page=has_next,
            has_previous_page=after is not None,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=end_cursor,
        ),
        total_count=total,
    )


async def resolve_exam(db: AsyncSession, exam_id: str) -> Optional[ExamType]:
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    e = result.scalar_one_or_none()
    return _exam_node(e) if e else None


async def resolve_exam_centers(db: AsyncSession) -> List[ExamCenterType]:
    rows = (await db.execute(select(ExamCenter))).scalars().all()
    return [_center_node(c) for c in rows]


async def resolve_nearby_centers(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float = 50.0,
) -> List[ExamCenterType]:
    rows = (await db.execute(select(ExamCenter))).scalars().all()
    results = []
    for c in rows:
        d = _haversine(latitude, longitude, c.latitude, c.longitude)
        if d <= radius_km:
            results.append(_center_node(c, round(d, 3)))
    results.sort(key=lambda x: x.distance_km or 0)
    return results


async def resolve_exam_slots(
    db: AsyncSession,
    starts_at: Optional[datetime] = None,
    ends_at: Optional[datetime] = None,
    exam_id: Optional[str] = None,
) -> List[ExamSlotType]:
    conditions = []
    if starts_at:
        conditions.append(ExamSlot.ends_at > starts_at)
    if ends_at:
        conditions.append(ExamSlot.starts_at < ends_at)
    if exam_id:
        conditions.append(ExamSlot.exam_id == exam_id)

    q = select(ExamSlot)
    if conditions:
        q = q.where(and_(*conditions))
    q = q.order_by(ExamSlot.starts_at.asc())

    rows = (await db.execute(q)).scalars().all()
    return [
        ExamSlotType(
            id=s.id, exam_id=s.exam_id, center_id=s.center_id,
            starts_at=s.starts_at, ends_at=s.ends_at,
            capacity=s.capacity, available_seats=s.available_seats,
        )
        for s in rows
    ]


async def resolve_my_registrations(
    db: AsyncSession, student_id: str
) -> List[RegistrationType]:
    rows = (
        await db.execute(
            select(Registration)
            .where(Registration.student_id == student_id)
            .order_by(Registration.registered_at.desc())
        )
    ).scalars().all()
    return [
        RegistrationType(
            id=r.id, student_id=r.student_id, slot_id=r.slot_id,
            status=r.status, score=r.score, grade=r.grade,
            registered_at=r.registered_at,
        )
        for r in rows
    ]
