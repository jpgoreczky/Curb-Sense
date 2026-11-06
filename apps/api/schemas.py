from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Status = Literal["available", "conditional", "restricted"]
CurbSide = Literal["left", "right"]
PinKind = Literal["point", "segment", "lot"]
VoteSide = Literal["tier1", "tier2", "unsure"]


class PinSummary(BaseModel):
    id: UUID
    kind: PinKind
    # Where to put the marker / label: the point itself, a segment's
    # midpoint, or a point inside a lot polygon.
    anchor_lon: float
    anchor_lat: float
    # Full GeoJSON geometry. For segments this is the street centerline
    # stretch; draw it with line-offset toward curb_side (positive = right).
    geometry: dict
    curb_side: CurbSide | None
    tier: int
    status: Status
    restrictions: dict
    last_verified_at: datetime | None
    display_priority: int
    street_name: str | None
    from_street: str | None
    to_street: str | None


class ReviewOut(BaseModel):
    id: UUID
    photo_url: str | None
    confirmed_fields: dict
    created_at: datetime


class OpenConflictOut(BaseModel):
    id: UUID
    tier1_snapshot: dict
    tier2_snapshot: dict
    opened_at: datetime
    decay_deadline: datetime


class PinDetail(PinSummary):
    reviews: list[ReviewOut]
    open_conflict: OpenConflictOut | None


class PinCreateRequest(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    status: Status
    restrictions: dict
    photo_url: str | None = None
    ai_extracted_fields: dict | None = None
    confirmed_fields: dict | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)


class ReviewCreateRequest(BaseModel):
    review_text: str = Field(min_length=1, max_length=2000)


class ConflictVoteRequest(BaseModel):
    # Which side the voter confirmed on the ground. The client derives this
    # from the drive-by prompt ("Is parking still restricted here?") by
    # comparing the answer with open_conflict.tier1/tier2_snapshot.
    supports: VoteSide


class ConflictResolveRequest(BaseModel):
    resolution: str
    resulting_status: Status
    resulting_restrictions: dict
