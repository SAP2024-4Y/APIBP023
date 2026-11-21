"""
Calendar API — exam slot time-window queries and registration with conflict prevention.

POST   /api/v1/exam-slots                  – create a slot (instructor/admin)
GET    /api/v1/exam-slots                  – list slots filtered by starts_at / ends_at
GET    /api/v1/exam-slots/{id}             – single slot
PATCH  /api/v1/exam-slots/{id}             – update capacity/times (instructor/admin)
POST   /api/v1/exam-slots/{id}/register    – book a slot (auth required; 409 on conflict)
DELETE /api/v1/exam-slots/{id}/register    – cancel own registration (auth required)
"""
import uuid as _uuid_mod
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..helpers.slots import check_slot_overlap
from ..middleware.rate_limit import limiter
from ..models import Exam, ExamCenter, ExamSlot, Registration, User

router = APIRouter(prefix="/exam-slots", tags=["exam-slots"])


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _slot_out(s: ExamSlot) -> dict:
    return {
        "id": s.id,
        "exam_id": s.exam_id,
        "center_id": s.center_id,
        "starts_at": s.starts_at.isoformat(),
        "ends_at": s.ends_at.isoformat(),
        "capacity": s.capacity,
        "available_seats": s.available_seats,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _reg_out(r: Registration) -> dict:
    return {
        "id": r.id,
        "student_id": r.student_id,
        "slot_id": r.slot_id,
        "status": r.status,
        "score": r.score,
        "grade": r.grade,
        "registered_at": r.registered_at.isoformat() if r.registered_at else None,
    }


# ---------------------------------------------------------------------------
# Conflict-detection helpers
# ---------------------------------------------------------------------------

async def _existing_registration(
    db: AsyncSession, student_id: str, slot_id: str
) -> Optional[Registration]:
    result = await db.execute(
        select(Registration).where(
            Registration.student_id == student_id,
            Registration.slot_id == slot_id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new exam slot")
@limiter.limit("30/minute")
async def create_slot(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("instructor", "admin")),
):
    body = await request.json()
    exam_id = body.get("exam_id")
    center_id = body.get("center_id")
    starts_at_str = body.get("starts_at")
    ends_at_str = body.get("ends_at")
    capacity = body.get("capacity")

    if not all([exam_id, center_id, starts_at_str, ends_at_str, capacity is not None]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": "exam_id, center_id, starts_at, ends_at, capacity are required"},
        )

    try:
        starts_at = datetime.fromisoformat(str(starts_at_str).replace("Z", "+00:00"))
        ends_at = datetime.fromisoformat(str(ends_at_str).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": "starts_at and ends_at must be ISO 8601 datetime strings"},
        )

    if starts_at >= ends_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DATE_RANGE", "message": "starts_at must be before ends_at"},
        )

    try:
        cap = int(capacity)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": "capacity must be a positive integer"},
        )
    if cap <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": "capacity must be a positive integer"},
        )

    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXAM_NOT_FOUND", "message": f"Exam '{exam_id}' not found"},
        )

    center = (await db.execute(select(ExamCenter).where(ExamCenter.id == center_id))).scalar_one_or_none()
    if not center:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CENTER_NOT_FOUND", "message": f"Exam center '{center_id}' not found"},
        )

    slot = ExamSlot(
        id=str(_uuid_mod.uuid4()),
        exam_id=exam_id,
        center_id=center_id,
        starts_at=starts_at,
        ends_at=ends_at,
        capacity=cap,
        available_seats=cap,
    )
    db.add(slot)
    await db.flush()
    await db.refresh(slot)
    return _slot_out(slot)


@router.get("", summary="List exam slots with optional time-window filter")
@limiter.limit("100/minute")
async def list_slots(
    request: Request,
    starts_at: Optional[datetime] = Query(None, description="ISO 8601 UTC window start"),
    ends_at: Optional[datetime] = Query(None, description="ISO 8601 UTC window end"),
    exam_id: Optional[str] = Query(None),
    center_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if starts_at and ends_at and starts_at >= ends_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DATE_RANGE", "message": "starts_at must be before ends_at"},
        )

    conditions = []
    if starts_at:
        conditions.append(ExamSlot.ends_at > starts_at)
    if ends_at:
        conditions.append(ExamSlot.starts_at < ends_at)
    if exam_id:
        conditions.append(ExamSlot.exam_id == exam_id)
    if center_id:
        conditions.append(ExamSlot.center_id == center_id)

    q = select(ExamSlot)
    if conditions:
        q = q.where(and_(*conditions))
    q = q.order_by(ExamSlot.starts_at.asc())

    rows = (await db.execute(q)).scalars().all()
    return {"data": [_slot_out(s) for s in rows], "count": len(rows)}


@router.get("/{slot_id}", summary="Get a single exam slot")
@limiter.limit("100/minute")
async def get_slot(request: Request, slot_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExamSlot).where(ExamSlot.id == slot_id))
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SLOT_NOT_FOUND", "message": f"Slot '{slot_id}' not found"},
        )
    return _slot_out(slot)


@router.patch("/{slot_id}", summary="Update an exam slot's capacity or time window")
@limiter.limit("30/minute")
async def update_slot(
    request: Request,
    slot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("instructor", "admin")),
):
    slot = (await db.execute(select(ExamSlot).where(ExamSlot.id == slot_id))).scalar_one_or_none()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SLOT_NOT_FOUND", "message": f"Slot '{slot_id}' not found"},
        )

    body = await request.json()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": "Provide at least one of: capacity, starts_at, ends_at"},
        )

    if "capacity" in body:
        try:
            new_cap = int(body["capacity"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "MISSING_FIELDS", "message": "capacity must be a positive integer"},
            )
        if new_cap <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "MISSING_FIELDS", "message": "capacity must be a positive integer"},
            )
        booked = slot.capacity - slot.available_seats
        if new_cap < booked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SLOT_CAPACITY_TOO_LOW",
                    "message": f"Cannot reduce capacity below {booked} (number of already-booked seats)",
                },
            )
        slot.available_seats = slot.available_seats + (new_cap - slot.capacity)
        slot.capacity = new_cap

    if "starts_at" in body or "ends_at" in body:
        try:
            new_starts = (
                datetime.fromisoformat(str(body["starts_at"]).replace("Z", "+00:00"))
                if "starts_at" in body else slot.starts_at
            )
            new_ends = (
                datetime.fromisoformat(str(body["ends_at"]).replace("Z", "+00:00"))
                if "ends_at" in body else slot.ends_at
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "MISSING_FIELDS", "message": "starts_at and ends_at must be ISO 8601 datetime strings"},
            )
        if new_starts >= new_ends:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_DATE_RANGE", "message": "starts_at must be before ends_at"},
            )
        slot.starts_at = new_starts
        slot.ends_at = new_ends

    await db.flush()
    return _slot_out(slot)


@router.post(
    "/{slot_id}/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register for an exam slot (conflict prevention — returns 409 on overlap or full slot)",
)
@limiter.limit("30/minute")
async def register_for_slot(
    request: Request,
    slot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ExamSlot).where(ExamSlot.id == slot_id))
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SLOT_NOT_FOUND", "message": f"Slot '{slot_id}' not found"},
        )

    exam_result = await db.execute(select(Exam).where(Exam.id == slot.exam_id))
    exam = exam_result.scalar_one_or_none()
    if exam and exam.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EXAM_CANCELLED", "message": "Cannot register for a cancelled exam"},
        )

    existing = await _existing_registration(db, current_user.id, slot_id)
    if existing and existing.status != "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_REGISTERED", "message": "You are already registered for this slot"},
        )

    if slot.available_seats <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SLOT_FULL", "message": "No available seats in this slot"},
        )

    # 5. Scheduling-conflict check (overlapping time windows)
    conflict = await check_slot_overlap(db, current_user.id, slot)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SLOT_CONFLICT",
                "message": "You already have an exam scheduled that overlaps with this time window",
                "conflicting_registration_id": conflict.id,
            },
        )

    reg = Registration(student_id=current_user.id, slot_id=slot_id, status="registered")
    db.add(reg)
    slot.available_seats -= 1
    await db.flush()
    await db.refresh(reg)
    return _reg_out(reg)


@router.delete(
    "/{slot_id}/register",
    status_code=status.HTTP_200_OK,
    summary="Cancel your registration for an exam slot",
)
@limiter.limit("30/minute")
async def cancel_registration(
    request: Request,
    slot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reg = await _existing_registration(db, current_user.id, slot_id)
    if not reg or reg.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REGISTRATION_NOT_FOUND", "message": "No active registration found for this slot"},
        )

    reg.status = "cancelled"

    slot_result = await db.execute(select(ExamSlot).where(ExamSlot.id == slot_id))
    slot = slot_result.scalar_one_or_none()
    if slot:
        slot.available_seats += 1

    await db.flush()
    return {"message": "Registration cancelled", "registration_id": reg.id}
