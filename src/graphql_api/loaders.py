"""
DataLoaders — batch-load related objects to prevent N+1 queries.

Each loader accepts a list of IDs and returns results in the same order.
"""
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.dataloader import DataLoader

from ..models import Exam, ExamCenter, ExamSlot, Registration


async def _load_centers(ids: List[str], db: AsyncSession) -> List:
    rows = (await db.execute(select(ExamCenter).where(ExamCenter.id.in_(ids)))).scalars().all()
    by_id = {r.id: r for r in rows}
    return [by_id.get(i) for i in ids]


async def _load_exams(ids: List[str], db: AsyncSession) -> List:
    rows = (await db.execute(select(Exam).where(Exam.id.in_(ids)))).scalars().all()
    by_id = {r.id: r for r in rows}
    return [by_id.get(i) for i in ids]


async def _load_slots_for_exams(ids: List[str], db: AsyncSession) -> List[List]:
    rows = (await db.execute(select(ExamSlot).where(ExamSlot.exam_id.in_(ids)))).scalars().all()
    by_exam: dict = {i: [] for i in ids}
    for s in rows:
        by_exam[s.exam_id].append(s)
    return [by_exam[i] for i in ids]


async def _load_regs_for_students(ids: List[str], db: AsyncSession) -> List[List]:
    rows = (
        await db.execute(select(Registration).where(Registration.student_id.in_(ids)))
    ).scalars().all()
    by_student: dict = {i: [] for i in ids}
    for r in rows:
        by_student[r.student_id].append(r)
    return [by_student[i] for i in ids]


def build_loaders(db: AsyncSession) -> dict:
    return {
        "center": DataLoader(load_fn=lambda ids: _load_centers(ids, db)),
        "exam": DataLoader(load_fn=lambda ids: _load_exams(ids, db)),
        "slots_for_exam": DataLoader(load_fn=lambda ids: _load_slots_for_exams(ids, db)),
        "regs_for_student": DataLoader(load_fn=lambda ids: _load_regs_for_students(ids, db)),
    }
