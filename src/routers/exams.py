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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models import Exam, User

router = APIRouter(prefix="/exams", tags=["exams"])

_SORTABLE = {"created_at", "fee", "title", "subject", "duration_minutes", "total_marks"}


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

def _encode_cursor(exam_id: str, created_at: datetime) -> str:
    raw = json.dumps({"id": exam_id, "ts": created_at.isoformat()})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str):
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor).decode())
        return data["id"], datetime.fromisoformat(data["ts"])
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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

    # RateLimit headers are added by slowapi middleware; add defaults for non-limited responses
    return {
        "data": [_exam_out(e) for e in rows],
        "has_more": has_more,
        "next_cursor": next_cursor,
        "limit": limit,
    }


@router.get("/{exam_id}", summary="Get a single exam by ID")
@limiter.limit("100/minute")
async def get_exam(
    request: Request,
    exam_id: str,
    db: AsyncSession = Depends(get_db),
):
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
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("instructor", "admin")),
):
    required = {"title", "subject", "duration_minutes", "total_marks", "passing_marks", "fee"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": f"Missing: {', '.join(missing)}"},
        )
    exam = Exam(
        title=body["title"],
        subject=body["subject"],
        description=body.get("description"),
        duration_minutes=int(body["duration_minutes"]),
        total_marks=int(body["total_marks"]),
        passing_marks=int(body["passing_marks"]),
        fee=float(body["fee"]),
        status=body.get("status", "scheduled"),
        created_by=current_user.id,
    )
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    return _exam_out(exam)
