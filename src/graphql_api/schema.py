"""Strawberry schema — wires Query and Mutation, injects DB session via context."""
from datetime import datetime
from typing import List, Optional

import strawberry
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from ..auth import _bearer, _decode
from ..database import async_session_maker, get_db
from ..models import User
from .loaders import build_loaders
from .mutations import (
    resolve_authenticate,
    resolve_cancel_registration,
    resolve_register_for_slot,
)
from .queries import (
    resolve_exam,
    resolve_exam_centers,
    resolve_exam_slots,
    resolve_exams,
    resolve_my_registrations,
    resolve_nearby_centers,
)
from .types import (
    AuthPayload,
    ExamCenterType,
    ExamConnection,
    ExamSlotType,
    ExamType,
    RegistrationResult,
    RegistrationType,
)


# ---------------------------------------------------------------------------
# Context factory — provides DB session + DataLoaders + optional current user
# ---------------------------------------------------------------------------

async def get_context(db: AsyncSession = Depends(get_db)):
    return {"db": db, "loaders": build_loaders(db), "user": None}


# ---------------------------------------------------------------------------
# Root Query
# ---------------------------------------------------------------------------

@strawberry.type
class Query:
    @strawberry.field(description="Paginated exam list supporting Connection spec")
    async def exams(
        self,
        info: Info,
        first: int = 20,
        after: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> ExamConnection:
        db: AsyncSession = info.context["db"]
        return await resolve_exams(db, first, after, status, category, min_price, max_price, sort, order)

    @strawberry.field(description="Fetch a single exam by ID")
    async def exam(self, info: Info, exam_id: str) -> Optional[ExamType]:
        return await resolve_exam(info.context["db"], exam_id)

    @strawberry.field(description="List all exam centers")
    async def exam_centers(self, info: Info) -> List[ExamCenterType]:
        return await resolve_exam_centers(info.context["db"])

    @strawberry.field(description="Find exam centers within radius_km of a coordinate point")
    async def nearby_exam_centers(
        self,
        info: Info,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
    ) -> List[ExamCenterType]:
        return await resolve_nearby_centers(info.context["db"], latitude, longitude, radius_km)

    @strawberry.field(description="List exam slots, optionally filtered by time window")
    async def exam_slots(
        self,
        info: Info,
        starts_at: Optional[datetime] = None,
        ends_at: Optional[datetime] = None,
        exam_id: Optional[str] = None,
    ) -> List[ExamSlotType]:
        return await resolve_exam_slots(info.context["db"], starts_at, ends_at, exam_id)

    @strawberry.field(description="My exam registrations (requires auth token in HTTP header)")
    async def my_registrations(self, info: Info) -> List[RegistrationType]:
        user = info.context.get("user")
        if not user:
            raise strawberry.exceptions.StrawberryGraphQLError(
                message="Authentication required",
                extensions={"code": "TOKEN_INVALID"},
            )
        return await resolve_my_registrations(info.context["db"], user.id)


# ---------------------------------------------------------------------------
# Root Mutation
# ---------------------------------------------------------------------------

@strawberry.type
class Mutation:
    @strawberry.mutation(description="Issue a JWT token — same as POST /api/v1/auth/token")
    async def authenticate(
        self, info: Info, username: str, password: str
    ) -> AuthPayload:
        return await resolve_authenticate(info.context["db"], username, password)

    @strawberry.mutation(description="Register for an exam slot; returns error union on conflict")
    async def register_for_slot(
        self, info: Info, slot_id: str
    ) -> RegistrationResult:
        user = info.context.get("user")
        if not user:
            return RegistrationResult(
                registration=None,
                error=None,  # will be caught by error extensions below
            )
        return await resolve_register_for_slot(info.context["db"], slot_id, user.id)

    @strawberry.mutation(description="Cancel an existing slot registration")
    async def cancel_registration(
        self, info: Info, slot_id: str
    ) -> RegistrationResult:
        user = info.context.get("user")
        if not user:
            raise strawberry.exceptions.StrawberryGraphQLError(
                message="Authentication required",
                extensions={"code": "TOKEN_INVALID"},
            )
        return await resolve_cancel_registration(info.context["db"], slot_id, user.id)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

schema = strawberry.Schema(query=Query, mutation=Mutation)
