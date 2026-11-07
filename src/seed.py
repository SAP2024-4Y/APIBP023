"""Seed the database with sample data on first run."""
import uuid
from datetime import datetime, timezone, timedelta

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import async_session_maker
from .models import User, ExamCenter, Exam, ExamSlot

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _id() -> str:
    return str(uuid.uuid4())


def _dt(year: int, month: int, day: int, hour: int = 9) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

USERS = [
    {"id": "user-demo-0001", "username": "demo", "email": "demo@example.com",
     "full_name": "Demo Student", "role": "student", "password": "demo-password"},
    {"id": "user-admin-0001", "username": "admin", "email": "admin@example.com",
     "full_name": "Admin User", "role": "admin", "password": "admin-password"},
    {"id": "user-inst-0001", "username": "instructor1", "email": "instructor1@example.com",
     "full_name": "Priya Sharma", "role": "instructor", "password": "inst-password"},
]

CENTERS = [
    {"id": "ctr-001", "name": "Delhi Examination Centre",
     "address": "1 Connaught Place", "city": "New Delhi", "state": "Delhi",
     "longitude": 77.2090, "latitude": 28.6139, "capacity": 200},
    {"id": "ctr-002", "name": "Mumbai Examination Centre",
     "address": "5 Marine Drive", "city": "Mumbai", "state": "Maharashtra",
     "longitude": 72.8236, "latitude": 18.9220, "capacity": 150},
    {"id": "ctr-003", "name": "Bangalore Examination Centre",
     "address": "12 MG Road", "city": "Bangalore", "state": "Karnataka",
     "longitude": 77.5946, "latitude": 12.9716, "capacity": 180},
    {"id": "ctr-004", "name": "Chennai Examination Centre",
     "address": "3 Anna Salai", "city": "Chennai", "state": "Tamil Nadu",
     "longitude": 80.2707, "latitude": 13.0827, "capacity": 120},
    {"id": "ctr-005", "name": "Kolkata Examination Centre",
     "address": "7 Park Street", "city": "Kolkata", "state": "West Bengal",
     "longitude": 88.3639, "latitude": 22.5726, "capacity": 160},
]

EXAMS = [
    {"id": "exam-001", "title": "Class 12 Mathematics Board Exam",
     "subject": "Mathematics", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 250.0, "status": "scheduled"},
    {"id": "exam-002", "title": "Class 12 Physics Board Exam",
     "subject": "Physics", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 250.0, "status": "scheduled"},
    {"id": "exam-003", "title": "Class 12 Chemistry Board Exam",
     "subject": "Chemistry", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 250.0, "status": "scheduled"},
    {"id": "exam-004", "title": "Class 12 Biology Board Exam",
     "subject": "Biology", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 250.0, "status": "scheduled"},
    {"id": "exam-005", "title": "Class 12 Computer Science Board Exam",
     "subject": "Computer Science", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 300.0, "status": "scheduled"},
    {"id": "exam-006", "title": "Class 12 English Board Exam",
     "subject": "English", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 200.0, "status": "scheduled"},
    {"id": "exam-007", "title": "Class 12 History Board Exam",
     "subject": "History", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 200.0, "status": "scheduled"},
    {"id": "exam-008", "title": "Class 12 Geography Board Exam",
     "subject": "Geography", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 200.0, "status": "scheduled"},
    {"id": "exam-009", "title": "Class 12 Economics Board Exam",
     "subject": "Economics", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 225.0, "status": "scheduled"},
    {"id": "exam-010", "title": "Class 12 Hindi Board Exam",
     "subject": "Hindi", "duration_minutes": 180, "total_marks": 100,
     "passing_marks": 33, "fee": 200.0, "status": "scheduled"},
    {"id": "exam-011", "title": "JEE Main Mathematics",
     "subject": "Mathematics", "duration_minutes": 90, "total_marks": 100,
     "passing_marks": 40, "fee": 650.0, "status": "scheduled"},
    {"id": "exam-012", "title": "JEE Main Physics",
     "subject": "Physics", "duration_minutes": 90, "total_marks": 100,
     "passing_marks": 40, "fee": 650.0, "status": "scheduled"},
    {"id": "exam-013", "title": "NEET Biology",
     "subject": "Biology", "duration_minutes": 200, "total_marks": 720,
     "passing_marks": 360, "fee": 800.0, "status": "scheduled"},
    {"id": "exam-014", "title": "NEET Chemistry",
     "subject": "Chemistry", "duration_minutes": 200, "total_marks": 180,
     "passing_marks": 90, "fee": 800.0, "status": "scheduled"},
    {"id": "exam-015", "title": "Aptitude Test — Quantitative",
     "subject": "Aptitude", "duration_minutes": 120, "total_marks": 100,
     "passing_marks": 50, "fee": 150.0, "status": "scheduled"},
    {"id": "exam-016", "title": "Aptitude Test — Verbal",
     "subject": "Aptitude", "duration_minutes": 90, "total_marks": 80,
     "passing_marks": 40, "fee": 150.0, "status": "scheduled"},
    {"id": "exam-017", "title": "General Science Proficiency",
     "subject": "Science", "duration_minutes": 120, "total_marks": 100,
     "passing_marks": 45, "fee": 175.0, "status": "completed"},
    {"id": "exam-018", "title": "Social Studies Final",
     "subject": "Social Studies", "duration_minutes": 150, "total_marks": 100,
     "passing_marks": 35, "fee": 180.0, "status": "cancelled"},
    {"id": "exam-019", "title": "Advanced Mathematics Olympiad",
     "subject": "Mathematics", "duration_minutes": 240, "total_marks": 150,
     "passing_marks": 75, "fee": 500.0, "status": "scheduled"},
    {"id": "exam-020", "title": "Informatics Olympiad",
     "subject": "Computer Science", "duration_minutes": 300, "total_marks": 200,
     "passing_marks": 100, "fee": 450.0, "status": "scheduled"},
]

# 25 slots spread across centers and exams, all in 2027
SLOTS: list[dict] = []
_slot_data = [
    ("exam-001", "ctr-001", _dt(2027, 3, 1, 9),  _dt(2027, 3, 1, 12), 60),
    ("exam-001", "ctr-002", _dt(2027, 3, 2, 9),  _dt(2027, 3, 2, 12), 50),
    ("exam-002", "ctr-001", _dt(2027, 3, 3, 9),  _dt(2027, 3, 3, 12), 60),
    ("exam-002", "ctr-003", _dt(2027, 3, 3, 14), _dt(2027, 3, 3, 17), 40),
    ("exam-003", "ctr-002", _dt(2027, 3, 5, 9),  _dt(2027, 3, 5, 12), 50),
    ("exam-003", "ctr-004", _dt(2027, 3, 5, 14), _dt(2027, 3, 5, 17), 30),
    ("exam-004", "ctr-005", _dt(2027, 3, 7, 9),  _dt(2027, 3, 7, 12), 45),
    ("exam-005", "ctr-001", _dt(2027, 3, 8, 9),  _dt(2027, 3, 8, 12), 35),
    ("exam-006", "ctr-002", _dt(2027, 3, 10, 9), _dt(2027, 3, 10, 12), 55),
    ("exam-007", "ctr-003", _dt(2027, 3, 11, 9), _dt(2027, 3, 11, 12), 40),
    ("exam-008", "ctr-004", _dt(2027, 3, 12, 9), _dt(2027, 3, 12, 12), 30),
    ("exam-009", "ctr-005", _dt(2027, 3, 14, 9), _dt(2027, 3, 14, 12), 50),
    ("exam-010", "ctr-001", _dt(2027, 3, 15, 9), _dt(2027, 3, 15, 12), 60),
    ("exam-011", "ctr-002", _dt(2027, 4, 1, 9),  _dt(2027, 4, 1, 10, 30), 80),
    ("exam-011", "ctr-003", _dt(2027, 4, 2, 9),  _dt(2027, 4, 2, 10, 30), 80),
    ("exam-012", "ctr-001", _dt(2027, 4, 3, 9),  _dt(2027, 4, 3, 10, 30), 80),
    ("exam-013", "ctr-004", _dt(2027, 5, 5, 8),  _dt(2027, 5, 5, 11, 20), 100),
    ("exam-013", "ctr-005", _dt(2027, 5, 6, 8),  _dt(2027, 5, 6, 11, 20), 100),
    ("exam-014", "ctr-002", _dt(2027, 5, 7, 8),  _dt(2027, 5, 7, 11, 20), 90),
    ("exam-015", "ctr-001", _dt(2027, 6, 1, 10), _dt(2027, 6, 1, 12), 70),
    ("exam-016", "ctr-003", _dt(2027, 6, 2, 10), _dt(2027, 6, 2, 11, 30), 65),
    ("exam-019", "ctr-001", _dt(2027, 7, 10, 9), _dt(2027, 7, 10, 13), 40),
    ("exam-019", "ctr-002", _dt(2027, 7, 11, 9), _dt(2027, 7, 11, 13), 40),
    ("exam-020", "ctr-003", _dt(2027, 8, 5, 9),  _dt(2027, 8, 5, 14), 50),
    ("exam-020", "ctr-004", _dt(2027, 8, 6, 9),  _dt(2027, 8, 6, 14), 50),
]
for i, (eid, cid, s, e, cap) in enumerate(_slot_data, 1):
    SLOTS.append({
        "id": f"slot-{i:03d}",
        "exam_id": eid,
        "center_id": cid,
        "starts_at": s,
        "ends_at": e,
        "capacity": cap,
        "available_seats": cap,
    })


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_seed() -> None:
    async with async_session_maker() as db:
        # Skip if already seeded
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none():
            return

        admin_id = "user-admin-0001"

        for u in USERS:
            db.add(User(
                id=u["id"],
                username=u["username"],
                email=u["email"],
                full_name=u["full_name"],
                role=u["role"],
                password_hash=_pwd.hash(u["password"]),
            ))

        for c in CENTERS:
            db.add(ExamCenter(**c))

        for e in EXAMS:
            db.add(Exam(**e, created_by=admin_id))

        for s in SLOTS:
            db.add(ExamSlot(**s))

        await db.commit()
