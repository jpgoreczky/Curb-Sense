from datetime import datetime, timezone

from geoalchemy2 import Geography
from sqlalchemy import cast, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import community_reports, conflicts, pin_features

_PIN_COLUMNS = (
    pin_features.c.id,
    pin_features.c.kind,
    pin_features.c.anchor_lon,
    pin_features.c.anchor_lat,
    pin_features.c.geometry,
    pin_features.c.curb_side,
    pin_features.c.tier,
    pin_features.c.status,
    pin_features.c.restrictions,
    pin_features.c.last_verified_at,
    pin_features.c.display_priority,
    pin_features.c.street_name,
    pin_features.c.from_street,
    pin_features.c.to_street,
)


async def get_pins_in_bbox(
    session: AsyncSession,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    limit: int = 500,
) -> list[dict]:
    """
    Viewport query against pin_features. `&&` on the geography column uses
    the GiST index (idx_parking_locations_geom). Ordering by display_priority
    means that when LIMIT truncates a dense viewport, Tier 3 and Tier 1 survive
    and Tier 2 is what gets dropped.
    """
    envelope = cast(func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326), Geography(srid=4326))
    stmt = (
        select(*_PIN_COLUMNS)
        .where(pin_features.c.geom.op("&&")(envelope))
        .order_by(pin_features.c.display_priority, pin_features.c.last_verified_at.desc().nulls_last())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result]


# Clustering applies below this zoom; at or above it the app renders raw
# features from get_pins_in_bbox. Mirrored by the mobile app (PRD 3.1).
RAW_MIN_ZOOM = 14

_CLUSTERS_SQL = text(
    "select cell_x, cell_y, lon, lat, count_all, count_verified, count_free, "
    "rep_all, rep_verified, rep_free "
    "from pin_clusters(CAST(:min_lon AS double precision), CAST(:min_lat AS double precision), "
    "CAST(:max_lon AS double precision), CAST(:max_lat AS double precision), CAST(:zoom AS integer))"
)


async def get_pin_clusters(
    session: AsyncSession,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    zoom: int,
) -> list[dict]:
    """
    Grid clusters for a viewport below street zoom. All bucketing, counting
    and representative selection happens in pin_clusters() (PostGIS); this
    only reshapes rows for the response.
    """
    rows = await session.execute(
        _CLUSTERS_SQL,
        {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat, "zoom": zoom},
    )
    return [
        {
            "cell": f"{zoom}/{r.cell_x}/{r.cell_y}",
            "lon": r.lon,
            "lat": r.lat,
            "counts": {"all": r.count_all, "verified": r.count_verified, "free": r.count_free},
            "representatives": {"all": r.rep_all, "verified": r.rep_verified, "free": r.rep_free},
        }
        for r in rows
    ]


async def get_pin_detail(session: AsyncSession, pin_id: str) -> dict | None:
    pin_row = (await session.execute(select(*_PIN_COLUMNS).where(pin_features.c.id == pin_id))).first()
    if pin_row is None:
        return None

    # user_id is deliberately not selected: public detail must not expose
    # who reported what, where and when.
    reviews_result = await session.execute(
        select(
            community_reports.c.id,
            community_reports.c.photo_url,
            community_reports.c.confirmed_fields,
            community_reports.c.created_at,
        )
        .where(community_reports.c.parking_location_id == pin_id)
        .order_by(community_reports.c.created_at.desc())
    )

    conflict_row = (
        await session.execute(
            select(
                conflicts.c.id,
                conflicts.c.tier1_snapshot,
                conflicts.c.tier2_snapshot,
                conflicts.c.opened_at,
                conflicts.c.decay_deadline,
            ).where(conflicts.c.parking_location_id == pin_id, conflicts.c.status == "open")
        )
    ).first()

    pin = dict(pin_row._mapping)
    pin["reviews"] = [dict(row._mapping) for row in reviews_result]
    pin["open_conflict"] = dict(conflict_row._mapping) if conflict_row else None
    return pin


async def add_review(
    session: AsyncSession,
    pin_id: str,
    user_id: str,
    review_text: str,
) -> dict:
    """
    Freeform qualitative feedback on an existing pin. Deliberately does NOT
    go through ingest_tier2: a review asserts no status/restriction data, so
    there's nothing to reconcile. Shape: no ai_extracted_fields, and
    confirmed_fields = {"type": "review", "review_text": ...}.
    """
    now = datetime.now(timezone.utc)
    review_id = (
        await session.execute(
            insert(community_reports)
            .values(
                parking_location_id=pin_id,
                user_id=user_id,
                confirmed_fields={"type": "review", "review_text": review_text},
                created_at=now,
            )
            .returning(community_reports.c.id)
        )
    ).scalar_one()
    await session.commit()
    return {"id": review_id, "parking_location_id": pin_id}
