"""
Calendar API — exam slot time-window queries and registration with conflict prevention.

GET  /api/v1/exam-slots                  – list slots filtered by starts_at / ends_at
GET  /api/v1/exam-slots/{id}             – single slot
POST /api/v1/exam-slots/{id}/register    – book a slot (auth required; 409 on conflict)
DELETE /api/v1/exam-slots/{id}/register  – cancel own registration (auth required)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
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

async def _check_overlap(
    db: AsyncSession,
    student_id: str,
    new_slot: ExamSlot,
) -> Optional[Registration]:
    """Return an existing active registration that overlaps with new_slot's time window."""
    result = await db.execute(
        select(Registration)
        .join(ExamSlot, Registration.slot_id == ExamSlot.id)
        .where(
            Registration.student_id == student_id,
            Registration.status.notin_(["cancelled"]),
            ExamSlot.starts_at < new_slot.ends_at,
            ExamSlot.ends_at > new_slot.starts_at,
        )
    )
    return result.scalar_one_or_none()


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
    # 1. Load the slot
    result = await db.execute(select(ExamSlot).where(ExamSlot.id == slot_id))
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SLOT_NOT_FOUND", "message": f"Slot '{slot_id}' not found"},
        )

    # 2. Check exam is bookable
    exam_result = await db.execute(select(Exam).where(Exam.id == slot.exam_id))
    exam = exam_result.scalar_one_or_none()
    if exam and exam.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EXAM_CANCELLED", "message": "Cannot register for a cancelled exam"},
        )

    # 3. Duplicate registration check
    existing = await _existing_registration(db, current_user.id, slot_id)
    if existing and existing.status != "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_REGISTERED", "message": "You are already registered for this slot"},
        )

    # 4. Seat availability check
    if slot.available_seats <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SLOT_FULL", "message": "No available seats in this slot"},
        )

    # 5. Scheduling-conflict check (overlapping time windows)
    conflict = await _check_overlap(db, current_user.id, slot)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SLOT_CONFLICT",
                "message": "You already have an exam scheduled that overlaps with this time window",
                "conflicting_registration_id": conflict.id,
            },
        )

    # 6. Create registration and decrement seat
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
