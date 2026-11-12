import uuid
from sqlalchemy import Boolean, Column, String, Float, Integer, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="student")  # student | instructor | admin
    created_at = Column(DateTime, server_default=func.now())

    registrations = relationship("Registration", back_populates="student")


class ExamCenter(Base):
    __tablename__ = "exam_centers"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    # GeoJSON convention: position = [longitude, latitude]
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    capacity = Column(Integer, nullable=False)
    contact_email = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    slots = relationship("ExamSlot", back_populates="center")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    subject = Column(String, nullable=False)   # maps to `category` query param
    description = Column(Text)
    duration_minutes = Column(Integer, nullable=False)
    total_marks = Column(Integer, nullable=False)
    passing_marks = Column(Integer, nullable=False)
    fee = Column(Float, nullable=False)        # maps to `min_price` / `max_price`
    status = Column(String, default="scheduled")  # scheduled | ongoing | completed | cancelled
    created_by = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())

    slots = relationship("ExamSlot", back_populates="exam")
    creator = relationship("User", foreign_keys=[created_by])
    questions = relationship("Question", back_populates="exam", order_by="Question.number")
    marking_policy = relationship("MarkingPolicy", back_populates="exam", uselist=False)


class ExamSlot(Base):
    __tablename__ = "exam_slots"

    id = Column(String, primary_key=True, default=_uuid)
    exam_id = Column(String, ForeignKey("exams.id"), nullable=False)
    center_id = Column(String, ForeignKey("exam_centers.id"), nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    capacity = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    exam = relationship("Exam", back_populates="slots")
    center = relationship("ExamCenter", back_populates="slots")
    registrations = relationship("Registration", back_populates="slot")


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(String, primary_key=True, default=_uuid)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    slot_id = Column(String, ForeignKey("exam_slots.id"), nullable=False)
    status = Column(String, default="registered")  # registered | confirmed | cancelled | completed
    score = Column(Float)
    grade = Column(String)
    registered_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "slot_id", name="uq_student_slot"),
    )

    student = relationship("User", back_populates="registrations")
    slot = relationship("ExamSlot", back_populates="registrations")
    answer_script = relationship("AnswerScript", back_populates="registration", uselist=False)


# ---------------------------------------------------------------------------
# Evaluation domain
# ---------------------------------------------------------------------------

class Question(Base):
    """A single question belonging to an exam."""
    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=_uuid)
    exam_id = Column(String, ForeignKey("exams.id"), nullable=False)
    number = Column(Integer, nullable=False)          # 1-based display order
    text = Column(Text, nullable=False)
    question_type = Column(String, nullable=False)    # mcq | integer | descriptive
    options = Column(Text)                            # JSON array for MCQ choices
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("exam_id", "number", name="uq_exam_question_number"),)

    exam = relationship("Exam", back_populates="questions")
    answer_key = relationship("AnswerKey", back_populates="question", uselist=False)
    student_answers = relationship("StudentAnswer", back_populates="question")


class MarkingPolicy(Base):
    """Per-exam marking rules applied during evaluation."""
    __tablename__ = "marking_policies"

    id = Column(String, primary_key=True, default=_uuid)
    exam_id = Column(String, ForeignKey("exams.id"), nullable=False, unique=True)
    marks_correct = Column(Float, nullable=False, default=4.0)   # marks per correct answer
    marks_wrong = Column(Float, nullable=False, default=-1.0)    # marks per wrong answer (negative = penalty)
    marks_unattempted = Column(Float, nullable=False, default=0.0)
    # For descriptive: partial credit threshold (0.0–1.0 keyword match ratio)
    partial_credit_threshold = Column(Float, nullable=False, default=0.5)
    partial_credit_ratio = Column(Float, nullable=False, default=0.5)  # fraction of marks_correct
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    exam = relationship("Exam", back_populates="marking_policy")


class AnswerKey(Base):
    """Correct answer for a question, set by instructors/admins."""
    __tablename__ = "answer_keys"

    id = Column(String, primary_key=True, default=_uuid)
    question_id = Column(String, ForeignKey("questions.id"), nullable=False, unique=True)
    correct_answer = Column(Text, nullable=False)   # MCQ: option letter; integer: number; descriptive: keywords JSON
    explanation = Column(Text)
    created_by = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    question = relationship("Question", back_populates="answer_key")
    creator = relationship("User")


class AnswerScript(Base):
    """A student's complete submission for a slot — one per (registration)."""
    __tablename__ = "answer_scripts"

    id = Column(String, primary_key=True, default=_uuid)
    registration_id = Column(String, ForeignKey("registrations.id"), nullable=False, unique=True)
    submitted_at = Column(DateTime, server_default=func.now())
    evaluated = Column(Boolean, nullable=False, default=False)
    evaluated_at = Column(DateTime)

    registration = relationship("Registration", back_populates="answer_script")
    student_answers = relationship("StudentAnswer", back_populates="script", cascade="all, delete-orphan")


class StudentAnswer(Base):
    """A student's answer to a single question within an AnswerScript."""
    __tablename__ = "student_answers"

    id = Column(String, primary_key=True, default=_uuid)
    script_id = Column(String, ForeignKey("answer_scripts.id"), nullable=False)
    question_id = Column(String, ForeignKey("questions.id"), nullable=False)
    answer = Column(Text)    # null = unattempted

    __table_args__ = (UniqueConstraint("script_id", "question_id", name="uq_script_question"),)

    script = relationship("AnswerScript", back_populates="student_answers")
    question = relationship("Question", back_populates="student_answers")
