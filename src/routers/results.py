"""
Results API — view evaluation results.

GET /api/v1/results/me                      – student: own evaluated registrations
GET /api/v1/results/registrations/{reg_id}  – student or admin: detailed result for one registration
GET /api/v1/results/exams/{exam_id}         – admin/instructor: all results for an exam (leaderboard)
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models import Exam, ExamSlot, Question, Registration, StudentAnswer, User

router = APIRouter(prefix="/results", tags=["results"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reg_summary(reg: Registration) -> dict:
    return {
        "registration_id": reg.id,
        "slot_id": reg.slot_id,
        "status": reg.status,
        "score": reg.score,
        "grade": reg.grade,
        "registered_at": reg.registered_at.isoformat() if reg.registered_at else None,
    }


async def _build_detail(reg: Registration, db: AsyncSession) -> dict:
    """Build a detailed result including per-question breakdown."""
    script = reg.answer_script
    if not script or not script.evaluated:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "NOT_EVALUATED", "message": "This registration has not been evaluated yet"})

    # Get exam
    slot = (await db.execute(select(ExamSlot).where(ExamSlot.id == reg.slot_id))).scalar_one_or_none()
    exam = (await db.execute(select(Exam).where(Exam.id == slot.exam_id))).scalar_one_or_none()

    # Get questions with answer keys
    questions = (await db.execute(
        select(Question)
        .where(Question.exam_id == exam.id)
        .options(selectinload(Question.answer_key))
        .order_by(Question.number)
    )).scalars().all()

    # Get student answers
    answers = {
        sa.question_id: sa.answer
        for sa in (await db.execute(
            select(StudentAnswer).where(StudentAnswer.script_id == script.id)
        )).scalars().all()
    }

    question_details = []
    for q in questions:
        correct = q.answer_key.correct_answer if q.answer_key else None
        student_ans = answers.get(q.id)
        question_details.append({
            "question_number": q.number,
            "question_text": q.text,
            "question_type": q.question_type,
            "student_answer": student_ans,
            "correct_answer": correct,
        })

    return {
        "registration_id": reg.id,
        "exam_id": exam.id,
        "exam_title": exam.title,
        "slot_id": reg.slot_id,
        "score": reg.score,
        "grade": reg.grade,
        "status": reg.status,
        "evaluated_at": script.evaluated_at.isoformat() if script.evaluated_at else None,
        "questions": question_details,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/me", summary="List all evaluated results for the current student")
@limiter.limit("60/minute")
async def my_results(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    regs = (await db.execute(
        select(Registration)
        .where(Registration.student_id == current_user.id, Registration.status == "completed")
        .options(selectinload(Registration.answer_script))
        .order_by(Registration.registered_at.desc())
    )).scalars().all()
    return {"data": [_reg_summary(r) for r in regs], "count": len(regs)}


@router.get("/registrations/{reg_id}", summary="Detailed result for a single registration")
@limiter.limit("60/minute")
async def get_result(
    request: Request,
    reg_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    reg = (await db.execute(
        select(Registration)
        .where(Registration.id == reg_id)
        .options(selectinload(Registration.answer_script))
    )).scalar_one_or_none()
    if not reg:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "REGISTRATION_NOT_FOUND", "message": "Registration not found"})
    if reg.student_id != current_user.id and current_user.role not in ("admin", "instructor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail={"code": "FORBIDDEN", "message": "You can only view your own results"})
    return await _build_detail(reg, db)


@router.get("/exams/{exam_id}", summary="All evaluated results for an exam (leaderboard)")
@limiter.limit("30/minute")
async def exam_results(
    request: Request,
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("instructor", "admin")),
) -> dict:
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "EXAM_NOT_FOUND", "message": f"Exam '{exam_id}' not found"})

    # Get all slots for this exam, then all completed registrations
    slot_ids = [
        s.id for s in (await db.execute(select(ExamSlot).where(ExamSlot.exam_id == exam_id))).scalars().all()
    ]
    if not slot_ids:
        return {"exam_id": exam_id, "data": [], "count": 0}

    regs = (await db.execute(
        select(Registration)
        .where(Registration.slot_id.in_(slot_ids), Registration.status == "completed")
        .options(selectinload(Registration.student))
        .order_by(Registration.score.desc())
    )).scalars().all()

    return {
        "exam_id": exam_id,
        "exam_title": exam.title,
        "data": [
            {
                "rank": i + 1,
                "student_id": r.student_id,
                "student_name": r.student.full_name if r.student else None,
                "slot_id": r.slot_id,
                "score": r.score,
                "grade": r.grade,
            }
            for i, r in enumerate(regs)
        ],
        "count": len(regs),
    }
