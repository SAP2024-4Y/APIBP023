from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ExamSlot, Registration


async def check_slot_overlap(
    db: AsyncSession,
    student_id: str,
    new_slot: ExamSlot,
) -> Optional[Registration]:
    result = await db.execute(
        select(Registration)
        .join(ExamSlot, Registration.slot_id == ExamSlot.id)
        .where(
            Registration.student_id == student_id,
            Registration.status.notin_(["cancelled"]),
            ExamSlot.starts_at < new_slot.ends_at,
            ExamSlot.ends_at > new_slot.starts_at,
        )
    )
    return result.scalar_one_or_none()
