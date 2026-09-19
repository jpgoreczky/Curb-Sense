from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PinSummary(BaseModel):
    id: UUID
    lon: float
    lat: float
    tier: int
    status: str
    restrictions: dict
    last_verified_at: datetime | None


class ReviewOut(BaseModel):
    id: UUID
    user_id: UUID
    photo_url: str | None
    confirmed_fields: dict
    created_at: datetime


class PinDetail(PinSummary):
    reviews: list[ReviewOut]


class PinCreateRequest(BaseModel):
    user_id: UUID  # TODO(BACK-2.5): derive from auth token, not request body
    lon: float
    lat: float
    status: str
    restrictions: dict
    photo_url: str | None = None
    ai_extracted_fields: dict | None = None
    confirmed_fields: dict | None = None
    confidence_score: float | None = None


class ReviewCreateRequest(BaseModel):
    user_id: UUID  # TODO(BACK-2.5): derive from auth token, not request body
    review_text: str


class ConflictResolveRequest(BaseModel):
    resolved_by: UUID  # TODO(BACK-2.5): derive from auth token, not request body
    resolution: str
    resulting_status: str
    resulting_restrictions: dict