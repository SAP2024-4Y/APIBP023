"""GraphQL mutations (state-changing operations)."""
import strawberry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_access_token, verify_password
from ..models import Exam, ExamSlot, Registration, User
from .types import AuthPayload, GraphQLError, RegistrationResult, RegistrationType


async def resolve_authenticate(
    db: AsyncSession, username: str, password: str
) -> AuthPayload:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise strawberry.exceptions.StrawberryGraphQLError(
            message="Invalid credentials",
            extensions={"code": "INVALID_CREDENTIALS"},
        )
    return AuthPayload(
        token=create_access_token(user.id, user.role),
        token_type="bearer",
        expires_in=28800,
    )


async def resolve_register_for_slot(
    db: AsyncSession,
    slot_id: str,
    student_id: str,
) -> RegistrationResult:
    # Load slot
    slot = (await db.execute(select(ExamSlot).where(ExamSlot.id == slot_id))).scalar_one_or_none()
    if not slot:
        return RegistrationResult(
            registration=None,
            error=GraphQLError(code="SLOT_NOT_FOUND", message=f"Slot '{slot_id}' not found"),
        )

    # Exam cancelled?
    exam = (await db.execute(select(Exam).where(Exam.id == slot.exam_id))).scalar_one_or_none()
    if exam and exam.status == "cancelled":
        return RegistrationResult(
            registration=None,
            error=GraphQLError(code="EXAM_CANCELLED", message="Cannot register for a cancelled exam"),
        )

    # Duplicate registration?
    existing = (
        await db.execute(
            select(Registration).where(
                Registration.student_id == student_id,
                Registration.slot_id == slot_id,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.status != "cancelled":
        return RegistrationResult(
            registration=None,
            error=GraphQLError(code="ALREADY_REGISTERED", message="Already registered for this slot"),
        )

    # Seat check
    if slot.available_seats <= 0:
        return RegistrationResult(
            registration=None,
            error=GraphQLError(code="SLOT_FULL", message="No available seats"),
        )

    # Overlap check
    overlap = (
        await db.execute(
            select(Registration)
            .join(ExamSlot, Registration.slot_id == ExamSlot.id)
            .where(
                Registration.student_id == student_id,
                Registration.status.notin_(["cancelled"]),
                ExamSlot.starts_at < slot.ends_at,
                ExamSlot.ends_at > slot.starts_at,
            )
        )
    ).scalar_one_or_none()
    if overlap:
        return RegistrationResult(
            registration=None,
            error=GraphQLError(
                code="SLOT_CONFLICT",
                message="Overlapping exam already scheduled",
            ),
        )

    reg = Registration(student_id=student_id, slot_id=slot_id, status="registered")
    db.add(reg)
    slot.available_seats -= 1
    await db.flush()
    await db.refresh(reg)

    return RegistrationResult(
        registration=RegistrationType(
            id=reg.id, student_id=reg.student_id, slot_id=reg.slot_id,
            status=reg.status, score=reg.score, grade=reg.grade,
            registered_at=reg.registered_at,
        ),
        error=None,
    )


async def resolve_cancel_registration(
    db: AsyncSession,
    slot_id: str,
    student_id: str,
) -> RegistrationResult:
    reg = (
        await db.execute(
            select(Registration).where(
                Registration.student_id == student_id,
                Registration.slot_id == slot_id,
            )
        )
    ).scalar_one_or_none()

    if not reg or reg.status == "cancelled":
        return RegistrationResult(
            registration=None,
            error=GraphQLError(code="REGISTRATION_NOT_FOUND", message="No active registration found"),
        )

    reg.status = "cancelled"
    slot = (await db.execute(select(ExamSlot).where(ExamSlot.id == slot_id))).scalar_one_or_none()
    if slot:
        slot.available_seats += 1
    await db.flush()

    return RegistrationResult(
        registration=RegistrationType(
            id=reg.id, student_id=reg.student_id, slot_id=reg.slot_id,
            status=reg.status, score=reg.score, grade=reg.grade,
            registered_at=reg.registered_at,
        ),
        error=None,
    )
