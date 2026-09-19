from geoalchemy2.functions import ST_MakeEnvelope, ST_Intersects, ST_X, ST_Y
from sqlalchemy import select, cast
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2 import Geography, Geometry
from datetime import datetime, timezone
from sqlalchemy import insert

from models import community_reports
from models import parking_locations


async def get_pins_in_bbox(
    session: AsyncSession,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    limit: int = 500,
) -> list[dict]:
    """
    Returns pins within the given bounding box.

    Uses ST_MakeEnvelope to build the viewport rectangle and ST_Intersects
    against it — PostGIS uses the GIST index (idx_parking_locations_geom,
    from BACK-2.1) to accelerate this via the underlying && operator,
    so this stays fast even as the pin count grows.
    """
    envelope = cast(
        ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326),
        Geography(srid=4326),
    )

    stmt = (
        select(
            parking_locations.c.id,
            ST_X(parking_locations.c.geom.cast(Geometry)).label("lon"),
            ST_Y(parking_locations.c.geom.cast(Geometry)).label("lat"),
            parking_locations.c.tier,
            parking_locations.c.status,
            parking_locations.c.restrictions,
            parking_locations.c.last_verified_at,
        )
        .where(ST_Intersects(parking_locations.c.geom, envelope))
        .limit(limit)
    )

    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]

async def get_pin_detail(session: AsyncSession, pin_id: str) -> dict | None:
    stmt = select(
        parking_locations.c.id,
        ST_X(parking_locations.c.geom.cast(Geometry)).label("lon"),
        ST_Y(parking_locations.c.geom.cast(Geometry)).label("lat"),
        parking_locations.c.tier,
        parking_locations.c.status,
        parking_locations.c.restrictions,
        parking_locations.c.last_verified_at,
    ).where(parking_locations.c.id == pin_id)

    result = await session.execute(stmt)
    pin_row = result.first()
    if pin_row is None:
        return None

    reviews_stmt = select(
        community_reports.c.id,
        community_reports.c.user_id,
        community_reports.c.photo_url,
        community_reports.c.confirmed_fields,
        community_reports.c.created_at,
    ).where(community_reports.c.parking_location_id == pin_id)

    reviews_result = await session.execute(reviews_stmt)
    reviews = [dict(row._mapping) for row in reviews_result]

    pin = dict(pin_row._mapping)
    pin["reviews"] = reviews
    return pin


async def add_review(
    session: AsyncSession,
    pin_id: str,
    user_id: str,
    review_text: str,
) -> dict:
    """
    Freeform qualitative feedback on an existing pin. Deliberately does NOT
    go through ingest_tier2's spatial-matching/conflict-detection engine —
    a review doesn't assert new status/restriction data, so there's nothing
    to reconcile against Tier 1. Distinguished from a structured Tier 2
    submission by shape: no ai_extracted_fields, confirmed_fields carries
    {"type": "review", "review_text": ...}.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        insert(community_reports)
        .values(
            parking_location_id=pin_id,
            user_id=user_id,
            confirmed_fields={"type": "review", "review_text": review_text},
            created_at=now,
        )
        .returning(community_reports.c.id)
    )
    result = await session.execute(stmt)
    review_id = result.scalar_one()
    await session.commit()
    return {"id": review_id, "parking_location_id": pin_id}