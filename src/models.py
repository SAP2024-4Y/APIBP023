import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, ForeignKey, UniqueConstraint
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
