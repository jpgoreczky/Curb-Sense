from geoalchemy2.functions import ST_MakeEnvelope, ST_Intersects, ST_X, ST_Y
from sqlalchemy import select, cast
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2 import Geography, Geometry

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