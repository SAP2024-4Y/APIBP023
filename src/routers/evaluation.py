"""
Answer-key management API — questions, answer keys, marking policies, and evaluation trigger.

All write endpoints require instructor or admin role.

POST   /api/v1/evaluation/exams/{exam_id}/questions           – add a question
GET    /api/v1/evaluation/exams/{exam_id}/questions           – list questions
GET    /api/v1/evaluation/exams/{exam_id}/questions/{q_id}    – single question
DELETE /api/v1/evaluation/exams/{exam_id}/questions/{q_id}    – remove question

PUT    /api/v1/evaluation/questions/{q_id}/answer-key         – set/update answer key
GET    /api/v1/evaluation/questions/{q_id}/answer-key         – get answer key

POST   /api/v1/evaluation/exams/{exam_id}/marking-policy      – create policy
GET    /api/v1/evaluation/exams/{exam_id}/marking-policy      – get policy
PUT    /api/v1/evaluation/exams/{exam_id}/marking-policy      – update policy
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..engine import PolicyConfig, evaluate_script
from ..middleware.rate_limit import limiter
from ..models import AnswerKey, AnswerScript, Exam, MarkingPolicy, Question, Registration, StudentAnswer, User

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class QuestionIn(BaseModel):
    number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    question_type: str = Field(..., pattern="^(mcq|integer|descriptive)$")
    options: Optional[List[str]] = None   # required for MCQ


class QuestionOut(BaseModel):
    id: str
    exam_id: str
    number: int
    text: str
    question_type: str
    options: Optional[List[str]]
    has_answer_key: bool


class AnswerKeyIn(BaseModel):
    correct_answer: str = Field(..., min_length=1)
    explanation: Optional[str] = None


class AnswerKeyOut(BaseModel):
    id: str
    question_id: str
    correct_answer: str
    explanation: Optional[str]
    created_by: Optional[str]


class MarkingPolicyIn(BaseModel):
    marks_correct: float = Field(..., gt=0)
    marks_wrong: float = Field(..., le=0)
    marks_unattempted: float = 0.0
    partial_credit_threshold: float = Field(0.5, ge=0.0, le=1.0)
    partial_credit_ratio: float = Field(0.5, ge=0.0, le=1.0)


class MarkingPolicyOut(BaseModel):
    id: str
    exam_id: str
    marks_correct: float
    marks_wrong: float
    marks_unattempted: float
    partial_credit_threshold: float
    partial_credit_ratio: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q_out(q: Question) -> dict:
    opts = None
    if q.options:
        try:
            opts = json.loads(q.options)
        except Exception:
            opts = None
    return QuestionOut(
        id=q.id,
        exam_id=q.exam_id,
        number=q.number,
        text=q.text,
        question_type=q.question_type,
        options=opts,
        has_answer_key=q.answer_key is not None,
    ).model_dump()


def _ak_out(ak: AnswerKey) -> dict:
    return AnswerKeyOut(
        id=ak.id,
        question_id=ak.question_id,
        correct_answer=ak.correct_answer,
        explanation=ak.explanation,
        created_by=ak.created_by,
    ).model_dump()


def _mp_out(mp: MarkingPolicy) -> dict:
    return MarkingPolicyOut(
        id=mp.id,
        exam_id=mp.exam_id,
        marks_correct=mp.marks_correct,
        marks_wrong=mp.marks_wrong,
        marks_unattempted=mp.marks_unattempted,
        partial_credit_threshold=mp.partial_credit_threshold,
        partial_credit_ratio=mp.partial_credit_ratio,
    ).model_dump()


async def _get_exam_or_404(exam_id: str, db: AsyncSession) -> Exam:
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "EXAM_NOT_FOUND", "message": f"Exam '{exam_id}' not found"})
    return exam


async def _get_question_or_404(q_id: str, db: AsyncSession) -> Question:
    q = (await db.execute(
        select(Question).where(Question.id == q_id).options(selectinload(Question.answer_key))
    )).scalar_one_or_none()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "QUESTION_NOT_FOUND", "message": f"Question '{q_id}' not found"})
    return q


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

@router.post("/exams/{exam_id}/questions", status_code=status.HTTP_201_CREATED, summary="Add a question to an exam")
@limiter.limit("60/minute")
async def add_question(
    request: Request,
    exam_id: str,
    body: QuestionIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("instructor", "admin")),
) -> dict:
    await _get_exam_or_404(exam_id, db)

    # Validate MCQ has options
    if body.question_type == "mcq":
        if not body.options or len(body.options) < 2:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail={"code": "INVALID_OPTIONS", "message": "MCQ questions require at least 2 options"})

    # Enforce unique question numbers
    existing = (await db.execute(
        select(Question).where(Question.exam_id == exam_id, Question.number == body.number)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "DUPLICATE_QUESTION_NUMBER", "message": f"Question number {body.number} already exists for this exam"})

    q = Question(
        exam_id=exam_id,
        number=body.number,
        text=body.text,
        question_type=body.question_type,
        options=json.dumps(body.options) if body.options else None,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    # reload with answer_key for serialization
    q = await _get_question_or_404(q.id, db)
    return _q_out(q)


@router.get("/exams/{exam_id}/questions", summary="List all questions for an exam")
@limiter.limit("120/minute")
async def list_questions(
    request: Request,
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    await _get_exam_or_404(exam_id, db)
    rows = (await db.execute(
        select(Question).where(Question.exam_id == exam_id)
        .options(selectinload(Question.answer_key))
        .order_by(Question.number)
    )).scalars().all()
    return {"data": [_q_out(q) for q in rows], "count": len(rows)}


@router.get("/exams/{exam_id}/questions/{q_id}", summary="Get a single question")
@limiter.limit("120/minute")
async def get_question(
    request: Request,
    exam_id: str,
    q_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    q = await _get_question_or_404(q_id, db)
    if q.exam_id != exam_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "QUESTION_NOT_FOUND", "message": "Question not found for this exam"})
    return _q_out(q)


@router.delete("/exams/{exam_id}/questions/{q_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a question")
@limiter.limit("30/minute")
async def delete_question(
    request: Request,
    exam_id: str,
    q_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("instructor", "admin")),
):
    q = await _get_question_or_404(q_id, db)
    if q.exam_id != exam_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "QUESTION_NOT_FOUND", "message": "Question not found for this exam"})
    await db.delete(q)
    await db.commit()


# ---------------------------------------------------------------------------
# Answer Keys
# ---------------------------------------------------------------------------

@router.put("/questions/{q_id}/answer-key", summary="Set or update the answer key for a question")
@limiter.limit("60/minute")
async def set_answer_key(
    request: Request,
    q_id: str,
    body: AnswerKeyIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("instructor", "admin")),
) -> dict:
    q = await _get_question_or_404(q_id, db)

    existing = (await db.execute(select(AnswerKey).where(AnswerKey.question_id == q_id))).scalar_one_or_none()
    if existing:
        existing.correct_answer = body.correct_answer
        existing.explanation = body.explanation
        existing.created_by = current_user.id
        await db.commit()
        await db.refresh(existing)
        return _ak_out(existing)

    ak = AnswerKey(
        question_id=q_id,
        correct_answer=body.correct_answer,
        explanation=body.explanation,
        created_by=current_user.id,
    )
    db.add(ak)
    await db.commit()
    await db.refresh(ak)
    return _ak_out(ak)


@router.get("/questions/{q_id}/answer-key", summary="Get the answer key for a question")
@limiter.limit("120/minute")
async def get_answer_key(
    request: Request,
    q_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("instructor", "admin")),
) -> dict:
    await _get_question_or_404(q_id, db)
    ak = (await db.execute(select(AnswerKey).where(AnswerKey.question_id == q_id))).scalar_one_or_none()
    if not ak:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "ANSWER_KEY_NOT_FOUND", "message": "No answer key set for this question"})
    return _ak_out(ak)


# ---------------------------------------------------------------------------
# Marking Policy
# ---------------------------------------------------------------------------

@router.post("/exams/{exam_id}/marking-policy", status_code=status.HTTP_201_CREATED, summary="Create a marking policy for an exam")
@limiter.limit("30/minute")
async def create_marking_policy(
    request: Request,
    exam_id: str,
    body: MarkingPolicyIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("instructor", "admin")),
) -> dict:
    await _get_exam_or_404(exam_id, db)
    existing = (await db.execute(select(MarkingPolicy).where(MarkingPolicy.exam_id == exam_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "POLICY_EXISTS", "message": "Marking policy already exists; use PUT to update"})
    mp = MarkingPolicy(exam_id=exam_id, **body.model_dump())
    db.add(mp)
    await db.commit()
    await db.refresh(mp)
    return _mp_out(mp)


@router.get("/exams/{exam_id}/marking-policy", summary="Get marking policy for an exam")
@limiter.limit("120/minute")
async def get_marking_policy(
    request: Request,
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    await _get_exam_or_404(exam_id, db)
    mp = (await db.execute(select(MarkingPolicy).where(MarkingPolicy.exam_id == exam_id))).scalar_one_or_none()
    if not mp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "POLICY_NOT_FOUND", "message": "No marking policy set for this exam"})
    return _mp_out(mp)


@router.put("/exams/{exam_id}/marking-policy", summary="Update marking policy for an exam")
@limiter.limit("30/minute")
async def update_marking_policy(
    request: Request,
    exam_id: str,
    body: MarkingPolicyIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("instructor", "admin")),
) -> dict:
    await _get_exam_or_404(exam_id, db)
    mp = (await db.execute(select(MarkingPolicy).where(MarkingPolicy.exam_id == exam_id))).scalar_one_or_none()
    if not mp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "POLICY_NOT_FOUND", "message": "No marking policy found; use POST to create"})
    for k, v in body.model_dump().items():
        setattr(mp, k, v)
    await db.commit()
    await db.refresh(mp)
    return _mp_out(mp)


# ---------------------------------------------------------------------------
# Evaluate — trigger scoring for a single answer script
# ---------------------------------------------------------------------------

@router.post("/scripts/{script_id}/evaluate", summary="Score an answer script and store the result")
@limiter.limit("30/minute")
async def evaluate(
    request: Request,
    script_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("instructor", "admin")),
) -> dict:
    # Load the script with its registration
    script = (await db.execute(
        select(AnswerScript)
        .where(AnswerScript.id == script_id)
        .options(selectinload(AnswerScript.registration))
    )).scalar_one_or_none()
    if not script:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "SCRIPT_NOT_FOUND", "message": f"Script '{script_id}' not found"})
    if script.evaluated:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "ALREADY_EVALUATED", "message": "Script has already been evaluated"})

    reg: Registration = script.registration

    # Get exam via slot
    from ..models import ExamSlot
    slot = (await db.execute(select(ExamSlot).where(ExamSlot.id == reg.slot_id))).scalar_one_or_none()
    exam = (await db.execute(select(Exam).where(Exam.id == slot.exam_id))).scalar_one_or_none()

    # Marking policy — required
    policy_row = (await db.execute(select(MarkingPolicy).where(MarkingPolicy.exam_id == exam.id))).scalar_one_or_none()
    if not policy_row:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "POLICY_NOT_FOUND", "message": "No marking policy set for this exam"})

    # Load questions with their answer keys
    questions = (await db.execute(
        select(Question)
        .where(Question.exam_id == exam.id)
        .options(selectinload(Question.answer_key))
        .order_by(Question.number)
    )).scalars().all()

    # Load student answers
    student_rows = (await db.execute(
        select(StudentAnswer).where(StudentAnswer.script_id == script_id)
    )).scalars().all()
    student_map = {sa.question_id: sa.answer for sa in student_rows}

    # Build question dicts for engine
    q_dicts = [
        {
            "id": q.id,
            "number": q.number,
            "question_type": q.question_type,
            "answer_key_correct_answer": q.answer_key.correct_answer if q.answer_key else None,
        }
        for q in questions
    ]

    policy = PolicyConfig(
        marks_correct=policy_row.marks_correct,
        marks_wrong=policy_row.marks_wrong,
        marks_unattempted=policy_row.marks_unattempted,
        partial_credit_threshold=policy_row.partial_credit_threshold,
        partial_credit_ratio=policy_row.partial_credit_ratio,
    )

    result = evaluate_script(q_dicts, student_map, policy, exam.total_marks, exam.passing_marks)

    # Persist results
    from datetime import datetime, timezone
    script.evaluated = True
    script.evaluated_at = datetime.now(timezone.utc)

    reg.score = result.total_score
    reg.grade = result.grade
    reg.status = "completed"

    await db.commit()

    return {
        "script_id": script_id,
        "registration_id": reg.id,
        "total_score": result.total_score,
        "max_score": result.max_score,
        "percentage": result.percentage,
        "grade": result.grade,
        "question_results": [
            {
                "question_id": qr.question_id,
                "question_number": qr.question_number,
                "question_type": qr.question_type,
                "student_answer": qr.student_answer,
                "correct_answer": qr.correct_answer,
                "marks_awarded": qr.marks_awarded,
                "verdict": qr.verdict,
            }
            for qr in result.question_results
        ],
    }
