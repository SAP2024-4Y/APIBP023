"""
Registrations — view and manage your exam registrations.

GET  /api/v1/registrations        – list own registrations (auth required)
GET  /api/v1/registrations/{id}   – get single registration (auth required)
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models import Registration, User

router = APIRouter(prefix="/registrations", tags=["registrations"])


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


@router.get("", summary="List your exam registrations")
@limiter.limit("100/minute")
async def list_my_registrations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(Registration)
            .where(Registration.student_id == current_user.id)
            .order_by(Registration.registered_at.desc())
        )
    ).scalars().all()
    return {"data": [_reg_out(r) for r in rows], "count": len(rows)}


@router.get("/{reg_id}", summary="Get a single registration")
@limiter.limit("100/minute")
async def get_registration(
    request: Request,
    reg_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Registration).where(Registration.id == reg_id))
    reg = result.scalar_one_or_none()
    if not reg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REGISTRATION_NOT_FOUND", "message": f"Registration '{reg_id}' not found"},
        )
    if reg.student_id != current_user.id and current_user.role not in ("admin", "instructor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "You can only view your own registrations"},
        )
    return _reg_out(reg)
