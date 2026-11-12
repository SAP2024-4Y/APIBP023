"""
Answer submission API — students upload their answer scripts.

POST   /api/v1/submissions/{registration_id}          – submit/replace an answer script
GET    /api/v1/submissions/{registration_id}          – view own submission
GET    /api/v1/submissions/{registration_id}/answers  – list individual answers

Rules:
- Only the registered student (or admin) may submit/view a script.
- Re-submission before evaluation replaces the existing script (idempotent for the student).
- Once evaluated, re-submission is rejected with 409.
- Answers for questions not belonging to the exam are rejected.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models import AnswerScript, ExamSlot, Question, Registration, StudentAnswer, User

router = APIRouter(prefix="/submissions", tags=["submissions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AnswerIn(BaseModel):
    question_id: str
    answer: Optional[str] = None    # None = unattempted


class SubmissionIn(BaseModel):
    answers: List[AnswerIn]


class AnswerOut(BaseModel):
    question_id: str
    question_number: int
    answer: Optional[str]


class ScriptOut(BaseModel):
    id: str
    registration_id: str
    submitted_at: str
    evaluated: bool
    evaluated_at: Optional[str]
    answer_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_registration(reg_id: str, db: AsyncSession, current_user: User) -> Registration:
    reg = (await db.execute(
        select(Registration).where(Registration.id == reg_id)
        .options(selectinload(Registration.answer_script))
    )).scalar_one_or_none()
    if not reg:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "REGISTRATION_NOT_FOUND", "message": f"Registration '{reg_id}' not found"})
    if reg.student_id != current_user.id and current_user.role not in ("admin", "instructor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail={"code": "FORBIDDEN", "message": "You can only access your own submissions"})
    if reg.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "REGISTRATION_CANCELLED", "message": "Cannot submit for a cancelled registration"})
    return reg


def _script_out(script: AnswerScript, answer_count: int) -> dict:
    return ScriptOut(
        id=script.id,
        registration_id=script.registration_id,
        submitted_at=script.submitted_at.isoformat(),
        evaluated=script.evaluated,
        evaluated_at=script.evaluated_at.isoformat() if script.evaluated_at else None,
        answer_count=answer_count,
    ).model_dump()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/{registration_id}", summary="Submit or replace an answer script")
@limiter.limit("10/minute")
async def submit_answers(
    request: Request,
    registration_id: str,
    body: SubmissionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    reg = await _get_registration(registration_id, db, current_user)

    # Fetch exam questions to validate submitted question IDs
    slot = (await db.execute(
        select(ExamSlot).where(ExamSlot.id == reg.slot_id)
    )).scalar_one_or_none()
    if not slot:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "SLOT_NOT_FOUND", "message": "Slot not found"})

    valid_q_ids = {
        q.id for q in (await db.execute(
            select(Question).where(Question.exam_id == slot.exam_id)
        )).scalars().all()
    }

    if not valid_q_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "NO_QUESTIONS", "message": "This exam has no questions set yet"})

    # Reject invalid question IDs
    submitted_ids = {a.question_id for a in body.answers}
    invalid = submitted_ids - valid_q_ids
    if invalid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "INVALID_QUESTION_IDS",
                                    "message": f"Questions not part of this exam: {sorted(invalid)}"})

    # If already evaluated, block re-submission
    existing_script = reg.answer_script
    if existing_script and existing_script.evaluated:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "ALREADY_EVALUATED",
                                    "message": "Script has already been evaluated; re-submission is not allowed"})

    # Delete old script if present (cascade deletes student_answers)
    if existing_script:
        await db.delete(existing_script)
        await db.flush()

    # Create new script
    script = AnswerScript(
        registration_id=registration_id,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(script)
    await db.flush()   # get script.id before inserting children

    # Deduplicate answers (last one wins) then insert
    deduped: Dict[str, Optional[str]] = {}
    for a in body.answers:
        deduped[a.question_id] = a.answer

    for q_id, ans in deduped.items():
        db.add(StudentAnswer(script_id=script.id, question_id=q_id, answer=ans))

    await db.commit()
    await db.refresh(script)

    return _script_out(script, len(deduped))


@router.get("/{registration_id}", summary="Get submission status for a registration")
@limiter.limit("60/minute")
async def get_submission(
    request: Request,
    registration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    reg = await _get_registration(registration_id, db, current_user)
    script = reg.answer_script
    if not script:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "SCRIPT_NOT_FOUND", "message": "No submission found for this registration"})

    count = len((await db.execute(
        select(StudentAnswer).where(StudentAnswer.script_id == script.id)
    )).scalars().all())

    return _script_out(script, count)


@router.get("/{registration_id}/answers", summary="List all answers in a submission")
@limiter.limit("60/minute")
async def list_answers(
    request: Request,
    registration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    reg = await _get_registration(registration_id, db, current_user)
    script = reg.answer_script
    if not script:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "SCRIPT_NOT_FOUND", "message": "No submission found for this registration"})

    answers = (await db.execute(
        select(StudentAnswer, Question)
        .join(Question, StudentAnswer.question_id == Question.id)
        .where(StudentAnswer.script_id == script.id)
        .order_by(Question.number)
    )).all()

    return {
        "data": [
            AnswerOut(
                question_id=sa.question_id,
                question_number=q.number,
                answer=sa.answer,
            ).model_dump()
            for sa, q in answers
        ],
        "count": len(answers),
    }
