"""
Evaluation engine — pure functions that score a student's answer script.

Supports three question types:
  mcq         – exact match (case-insensitive, stripped)
  integer     – numeric equality
  descriptive – keyword match: count keywords from the answer key that
                appear in the student's response; if coverage ≥
                partial_credit_threshold → partial_credit_ratio * marks_correct;
                full keyword coverage → marks_correct

Grading scale applied after total score is computed:
  ≥ 90% of total_marks → A+
  ≥ 80%               → A
  ≥ 70%               → B+
  ≥ 60%               → B
  ≥ passing_marks %   → C  (pass threshold)
  < passing_marks %   → F

The engine is intentionally stateless — it takes plain data structures and
returns a result dict.  Persistence (updating Registration + AnswerScript) is
done by the caller in the router layer.
"""
import json
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class PolicyConfig:
    marks_correct: float
    marks_wrong: float
    marks_unattempted: float
    partial_credit_threshold: float
    partial_credit_ratio: float


@dataclass(frozen=True)
class QuestionResult:
    question_id: str
    question_number: int
    question_type: str
    student_answer: Optional[str]
    correct_answer: str
    marks_awarded: float
    verdict: str   # "correct" | "wrong" | "partial" | "unattempted" | "no_key"


@dataclass(frozen=True)
class EvaluationResult:
    total_score: float
    max_score: float
    percentage: float
    grade: str
    question_results: list


# ---------------------------------------------------------------------------
# Per-question scoring
# ---------------------------------------------------------------------------

def _score_mcq(student: Optional[str], correct: str, policy: PolicyConfig) -> tuple[float, str]:
    if student is None:
        return policy.marks_unattempted, "unattempted"
    if student.strip().upper() == correct.strip().upper():
        return policy.marks_correct, "correct"
    return policy.marks_wrong, "wrong"


def _score_integer(student: Optional[str], correct: str, policy: PolicyConfig) -> tuple[float, str]:
    if student is None:
        return policy.marks_unattempted, "unattempted"
    try:
        sv = float(student.strip())
        cv = float(correct.strip())
        if sv == cv:
            return policy.marks_correct, "correct"
        return policy.marks_wrong, "wrong"
    except ValueError:
        return policy.marks_wrong, "wrong"


def _score_descriptive(student: Optional[str], correct_keywords_json: str, policy: PolicyConfig) -> tuple[float, str]:
    """Keywords stored as a JSON array in correct_answer for descriptive questions."""
    if student is None:
        return policy.marks_unattempted, "unattempted"

    try:
        keywords: list = json.loads(correct_keywords_json)
    except (json.JSONDecodeError, TypeError):
        keywords = [correct_keywords_json]

    if not keywords:
        return policy.marks_unattempted, "unattempted"

    student_lower = student.lower()
    matched = sum(1 for kw in keywords if kw.lower() in student_lower)
    ratio = matched / len(keywords)

    if ratio >= 1.0:
        return policy.marks_correct, "correct"
    if ratio >= policy.partial_credit_threshold:
        return policy.marks_correct * policy.partial_credit_ratio, "partial"
    if ratio > 0:
        return policy.marks_wrong, "wrong"
    return policy.marks_unattempted, "unattempted"


def score_question(
    question_type: str,
    student_answer: Optional[str],
    correct_answer: str,
    policy: PolicyConfig,
) -> tuple[float, str]:
    if question_type == "mcq":
        return _score_mcq(student_answer, correct_answer, policy)
    if question_type == "integer":
        return _score_integer(student_answer, correct_answer, policy)
    if question_type == "descriptive":
        return _score_descriptive(student_answer, correct_answer, policy)
    # Unknown type — treat as unattempted
    return policy.marks_unattempted, "unattempted"


# ---------------------------------------------------------------------------
# Grade assignment
# ---------------------------------------------------------------------------

def assign_grade(score: float, max_score: float, passing_marks: int, total_marks: int) -> str:
    if max_score <= 0:
        return "F"
    pct = (score / max_score) * 100
    pass_pct = (passing_marks / total_marks) * 100

    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 70:
        return "B+"
    if pct >= 60:
        return "B"
    if pct >= pass_pct:
        return "C"
    return "F"


# ---------------------------------------------------------------------------
# Full script evaluation
# ---------------------------------------------------------------------------

def evaluate_script(
    questions: list,          # list of dicts: {id, number, question_type, answer_key_correct_answer}
    student_answers: Dict[str, Optional[str]],   # question_id → answer
    policy: PolicyConfig,
    total_marks: int,
    passing_marks: int,
) -> EvaluationResult:
    """
    questions: each must have keys id, number, question_type.
               answer_key_correct_answer may be None if no key set.
    student_answers: maps question_id to the student's answer (None = unattempted).
    """
    results = []
    total_score = 0.0

    for q in questions:
        q_id = q["id"]
        correct = q.get("answer_key_correct_answer")
        student = student_answers.get(q_id)

        if correct is None:
            marks, verdict = 0.0, "no_key"
        else:
            marks, verdict = score_question(q["question_type"], student, correct, policy)

        total_score += marks
        results.append(QuestionResult(
            question_id=q_id,
            question_number=q["number"],
            question_type=q["question_type"],
            student_answer=student,
            correct_answer=correct or "",
            marks_awarded=marks,
            verdict=verdict,
        ))

    # Max score = number of questions * marks_correct (questions without a key contribute 0)
    keyed_count = sum(1 for q in questions if q.get("answer_key_correct_answer") is not None)
    max_score = keyed_count * policy.marks_correct

    pct = round((total_score / max_score * 100) if max_score > 0 else 0.0, 2)
    grade = assign_grade(total_score, max_score, passing_marks, total_marks)

    return EvaluationResult(
        total_score=round(total_score, 2),
        max_score=max_score,
        percentage=pct,
        grade=grade,
        question_results=results,
    )
