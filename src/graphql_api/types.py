"""Strawberry GraphQL type definitions."""
from datetime import datetime
from typing import List, Optional

import strawberry


# ---------------------------------------------------------------------------
# Scalars / simple types
# ---------------------------------------------------------------------------

@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]


# ---------------------------------------------------------------------------
# Exam
# ---------------------------------------------------------------------------

@strawberry.type
class ExamType:
    id: str
    title: str
    category: str        # subject exposed as 'category' for the List pattern
    description: Optional[str]
    duration_minutes: int
    total_marks: int
    passing_marks: int
    fee: float
    status: str
    created_at: Optional[datetime]

    @strawberry.field(
        deprecation_reason="Use category instead — 'subject' will be removed in v2"
    )
    def subject(self) -> str:
        return self.category


@strawberry.type
class ExamEdge:
    node: ExamType
    cursor: str


@strawberry.type
class ExamConnection:
    edges: List[ExamEdge]
    page_info: PageInfo
    total_count: int


# ---------------------------------------------------------------------------
# ExamCenter
# ---------------------------------------------------------------------------

@strawberry.type
class CoordinatesType:
    """GeoJSON: position = [longitude, latitude]"""
    longitude: float
    latitude: float


@strawberry.type
class ExamCenterType:
    id: str
    name: str
    address: str
    city: str
    state: str
    capacity: int
    contact_email: Optional[str]
    coordinates: CoordinatesType
    distance_km: Optional[float] = None


# ---------------------------------------------------------------------------
# ExamSlot
# ---------------------------------------------------------------------------

@strawberry.type
class ExamSlotType:
    id: str
    exam_id: str
    center_id: str
    starts_at: datetime
    ends_at: datetime
    capacity: int
    available_seats: int


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@strawberry.type
class RegistrationType:
    id: str
    student_id: str
    slot_id: str
    status: str
    score: Optional[float]
    grade: Optional[str]
    registered_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@strawberry.type
class AuthPayload:
    token: str
    token_type: str
    expires_in: int


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

@strawberry.type
class GraphQLError:
    code: str
    message: str


@strawberry.type
class RegistrationResult:
    registration: Optional[RegistrationType]
    error: Optional[GraphQLError]
