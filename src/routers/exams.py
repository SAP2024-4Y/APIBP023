"""
List API — GET /api/v1/exams

Supports:
  Filtering : status, category (maps to subject), min_price, max_price
  Sorting   : sort=<field> + order=asc|desc
  Pagination: cursor-based via limit + after (opaque base-64 token)
"""
import base64
import json
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, model_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_roles
from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models import Exam, User

router = APIRouter(prefix="/exams", tags=["exams"])

_SORTABLE = {"created_at", "fee", "title", "subject", "duration_minutes", "total_marks"}

ExamStatus = Literal["draft", "published", "scheduled", "ongoing", "completed", "cancelled"]


class ExamCreate(BaseModel):
    title: str
    subject: str
    description: Optional[str] = None
    total_marks: float
    passing_marks: float
    duration_minutes: int
    fee: float = 0.0
    status: ExamStatus = "scheduled"

    @model_validator(mode="after")
    def check_values(self):
        if self.total_marks <= 0:
            raise ValueError("total_marks must be positive")
        if self.passing_marks <= 0:
            raise ValueError("passing_marks must be positive")
        if self.passing_marks > self.total_marks:
            raise ValueError("passing_marks cannot exceed total_marks")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if self.fee < 0:
            raise ValueError("fee cannot be negative")
        return self


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    total_marks: Optional[float] = None
    passing_marks: Optional[float] = None
    duration_minutes: Optional[int] = None
    fee: Optional[float] = None
    status: Optional[ExamStatus] = None


def _encode_cursor(exam_id: str, created_at: datetime) -> str:
    raw = json.dumps({"id": exam_id, "ts": created_at.isoformat()})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str):
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor).decode())
        return data["id"], datetime.fromisoformat(data["ts"])
    except Exception:
        return None, None


def _exam_out(e: Exam) -> dict:
    return {
        "id": e.id,
        "title": e.title,
        "category": e.subject,
        "subject": e.subject,
        "description": e.description,
        "duration_minutes": e.duration_minutes,
        "total_marks": e.total_marks,
        "passing_marks": e.passing_marks,
        "fee": e.fee,
        "status": e.status,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("", summary="List exams with filtering, sorting and cursor pagination")
@limiter.limit("100/minute")
async def list_exams(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(20, ge=1, le=100),
    after: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if sort not in _SORTABLE:
        sort = "created_at"
    conditions = []
    if status_filter:
        conditions.append(Exam.status == status_filter)
    if category:
        conditions.append(Exam.subject.ilike(f"%{category}%"))
    if min_price is not None:
        conditions.append(Exam.fee >= min_price)
    if max_price is not None:
        conditions.append(Exam.fee <= max_price)
    if after:
        cursor_id, cursor_ts = _decode_cursor(after)
        if cursor_ts:
            if order == "desc":
                conditions.append(
                    or_(
                        Exam.created_at < cursor_ts,
                        and_(Exam.created_at == cursor_ts, Exam.id < cursor_id),
                    )
                )
            else:
                conditions.append(
                    or_(
                        Exam.created_at > cursor_ts,
                        and_(Exam.created_at == cursor_ts, Exam.id > cursor_id),
                    )
                )
    q = select(Exam)
    if conditions:
        q = q.where(and_(*conditions))
    sort_col = getattr(Exam, sort)
    q = q.order_by(
        sort_col.desc() if order == "desc" else sort_col.asc(),
        Exam.id.desc() if order == "desc" else Exam.id.asc(),
    )
    q = q.limit(limit + 1)
    rows = (await db.execute(q)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last.id, last.created_at)
    return {"data": [_exam_out(e) for e in rows], "has_more": has_more, "next_cursor": next_cursor, "limit": limit}


@router.get("/{exam_id}", summary="Get a single exam by ID")
@limiter.limit("100/minute")
async def get_exam(request: Request, exam_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXAM_NOT_FOUND", "message": f"Exam '{exam_id}' not found"},
        )
    return _exam_out(exam)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new exam (instructor/admin)")
@limiter.limit("30/minute")
async def create_exam(
    request: Request,
    body: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("instructor", "admin")),
):
    exam = Exam(
        title=body.title,
        subject=body.subject,
        description=body.description,
        duration_minutes=body.duration_minutes,
        total_marks=body.total_marks,
        passing_marks=body.passing_marks,
        fee=body.fee,
        status=body.status,
        created_by=current_user.id,
    )
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    return _exam_out(exam)


@router.patch("/{exam_id}", summary="Update an exam (instructor/admin)")
@limiter.limit("30/minute")
async def update_exam(
    request: Request,
    exam_id: str,
    body: ExamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("instructor", "admin")),
):
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXAM_NOT_FOUND", "message": f"Exam '{exam_id}' not found"},
        )
    update_data = body.model_dump(exclude_none=True)
    new_total = update_data.get("total_marks", exam.total_marks)
    new_passing = update_data.get("passing_marks", exam.passing_marks)
    if new_passing > new_total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": "passing_marks cannot exceed total_marks"},
        )
    for field, value in update_data.items():
        setattr(exam, field, value)
    await db.flush()
    return _exam_out(exam)
