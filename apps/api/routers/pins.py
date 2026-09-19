from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db_session
from schemas import ConflictResolveRequest, PinCreateRequest, PinDetail, PinSummary, ReviewCreateRequest
from services.ingestion import ingest_tier2, resolve_conflict
from services.parking import add_review, get_pin_detail, get_pins_in_bbox

from uuid import UUID

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> None:
    try:
        UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format")


@router.get("/pins", response_model=list[PinSummary])
async def list_pins(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    session: AsyncSession = Depends(get_db_session),
):
    return await get_pins_in_bbox(session, min_lon, min_lat, max_lon, max_lat)


@router.get("/pins/{pin_id}", response_model=PinDetail)
async def get_pin(pin_id: str, session: AsyncSession = Depends(get_db_session)):
    _validate_uuid(pin_id, "pin_id")
    pin = await get_pin_detail(session, pin_id)
    if pin is None:
        raise HTTPException(status_code=404, detail="Pin not found")
    return pin


@router.post("/pins")
async def create_pin(payload: PinCreateRequest, session: AsyncSession = Depends(get_db_session)):
    result = await ingest_tier2(
        session,
        user_id=str(payload.user_id),
        lon=payload.lon,
        lat=payload.lat,
        status=payload.status,
        restrictions=payload.restrictions,
        photo_url=payload.photo_url,
        ai_extracted_fields=payload.ai_extracted_fields,
        confirmed_fields=payload.confirmed_fields,
        confidence_score=payload.confidence_score,
    )
    return result


@router.post("/pins/{pin_id}/reviews")
async def create_review(
    pin_id: str, payload: ReviewCreateRequest, session: AsyncSession = Depends(get_db_session)
):
    _validate_uuid(pin_id, "pin_id")
    existing = await get_pin_detail(session, pin_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Pin not found")
    return await add_review(session, pin_id, str(payload.user_id), payload.review_text)


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict_route(
    conflict_id: str, payload: ConflictResolveRequest, session: AsyncSession = Depends(get_db_session)
):
    _validate_uuid(conflict_id, "conflict_id")
    try:
        return await resolve_conflict(
            session,
            conflict_id=conflict_id,
            resolution=payload.resolution,
            resolved_by=str(payload.resolved_by),
            resulting_status=payload.resulting_status,
            resulting_restrictions=payload.resulting_restrictions,
        )
    except Exception as e:
        # NOTE: broad catch is temporary — resolve_conflict currently raises
        # a bare scalar_one() error if conflict_id doesn't exist, rather than
        # a clean domain exception. Worth revisiting for a proper 404 vs 500
        # distinction once error handling gets a real pass.
        raise HTTPException(status_code=400, detail=str(e))