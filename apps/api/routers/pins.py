from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user_id, require_ops_user_id
from db import get_db_session
from schemas import (
    ConflictResolveRequest,
    ConflictVoteRequest,
    PinCreateRequest,
    PinClusterResponse,
    PinDetail,
    PinSummary,
    ReviewCreateRequest,
)
from services.ingestion import (
    ConflictNotFound,
    ConflictNotOpen,
    cast_conflict_vote,
    ingest_tier2,
    resolve_conflict,
)
from services.parking import RAW_MIN_ZOOM, add_review, get_pin_clusters, get_pin_detail, get_pins_in_bbox

router = APIRouter()


# Guards against a huge bbox at a high zoom (thousands of cells). A phone
# viewport is roughly 8 x 16 cells at 64 px; this leaves room for tablets
# and prefetching neighbouring areas.
MAX_CLUSTER_SPAN_DEG_AT_Z0 = 360.0 * 4


# Must be registered before /pins/{pin_id}, or "clusters" parses as a UUID.
@router.get("/pins/clusters", response_model=PinClusterResponse)
async def list_pin_clusters(
    min_lon: float = Query(..., ge=-180, le=180),
    min_lat: float = Query(..., ge=-90, le=90),
    max_lon: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
    zoom: int = Query(..., ge=0, lt=RAW_MIN_ZOOM, description="Floor of the Mapbox camera zoom"),
    session: AsyncSession = Depends(get_db_session),
):
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="Bounding box min must be less than max")
    # Request-size check only (no spatial logic): the widest bbox allowed
    # shrinks by half per zoom level, like the visible area does.
    max_span = MAX_CLUSTER_SPAN_DEG_AT_Z0 / (2**zoom)
    if (max_lon - min_lon) > max_span or (max_lat - min_lat) > max_span:
        raise HTTPException(status_code=400, detail=f"Bounding box too large for zoom {zoom}")
    clusters = await get_pin_clusters(session, min_lon, min_lat, max_lon, max_lat, zoom)
    return {"zoom": zoom, "raw_min_zoom": RAW_MIN_ZOOM, "clusters": clusters}


@router.get("/pins", response_model=list[PinSummary])
async def list_pins(
    min_lon: float = Query(..., ge=-180, le=180),
    min_lat: float = Query(..., ge=-90, le=90),
    max_lon: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
    limit: int = Query(500, ge=1, le=2000),
    session: AsyncSession = Depends(get_db_session),
):
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="Bounding box min must be less than max")
    return await get_pins_in_bbox(session, min_lon, min_lat, max_lon, max_lat, limit)


@router.get("/pins/{pin_id}", response_model=PinDetail)
async def get_pin(pin_id: UUID, session: AsyncSession = Depends(get_db_session)):
    pin = await get_pin_detail(session, str(pin_id))
    if pin is None:
        raise HTTPException(status_code=404, detail="Pin not found")
    return pin


@router.post("/pins")
async def create_pin(
    payload: PinCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    return await ingest_tier2(
        session,
        user_id=user_id,
        lon=payload.lon,
        lat=payload.lat,
        status=payload.status,
        restrictions=payload.restrictions,
        photo_url=payload.photo_url,
        ai_extracted_fields=payload.ai_extracted_fields,
        confirmed_fields=payload.confirmed_fields,
        confidence_score=payload.confidence_score,
    )


@router.post("/pins/{pin_id}/reviews")
async def create_review(
    pin_id: UUID,
    payload: ReviewCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    existing = await get_pin_detail(session, str(pin_id))
    if existing is None:
        raise HTTPException(status_code=404, detail="Pin not found")
    return await add_review(session, str(pin_id), user_id, payload.review_text)


@router.post("/conflicts/{conflict_id}/votes")
async def vote_on_conflict(
    conflict_id: UUID,
    payload: ConflictVoteRequest,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await cast_conflict_vote(
            session, conflict_id=str(conflict_id), user_id=user_id, supports=payload.supports
        )
    except ConflictNotFound:
        raise HTTPException(status_code=404, detail="Conflict not found")
    except ConflictNotOpen:
        raise HTTPException(status_code=409, detail="Conflict is no longer open")


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict_route(
    conflict_id: UUID,
    payload: ConflictResolveRequest,
    session: AsyncSession = Depends(get_db_session),
    ops_user_id: str = Depends(require_ops_user_id),
):
    try:
        return await resolve_conflict(
            session,
            conflict_id=str(conflict_id),
            resolution=payload.resolution,
            resolved_by=ops_user_id,
            resulting_status=payload.resulting_status,
            resulting_restrictions=payload.resulting_restrictions,
        )
    except ConflictNotFound:
        raise HTTPException(status_code=404, detail="Conflict not found")
    except ConflictNotOpen:
        raise HTTPException(status_code=409, detail="Conflict is no longer open")
