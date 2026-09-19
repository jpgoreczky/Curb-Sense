"""
BACK-2.3: Three-tier data ingestion and conflict resolution engine.

Design notes (see conversation for full rationale):
- Location matching is spatial (ST_DWithin), not exact-coordinate, using a
  15m radius (DEFAULT_MATCH_RADIUS_M) to account for GPS/photo-geotag noise
  while staying tight enough to distinguish adjacent spots.
- Conflicts are only formally raised for Tier 1 vs. Tier 2 disagreement on
  status, per the PRD's own definition. Tier 2-vs-Tier 2 disagreement is
  informally latest-wins for now (GAM-6.1's contributor weighting is a
  separate, later concern).
- Tier 3 records are never silently overwritten — new incoming data during
  an open conflict only refreshes that side's snapshot; resolution is a
  deliberate, separate action (resolve_conflict), never automatic.
- decay_deadline defaults to 48 hours, matching the PRD's own
  "Conflict Resolution Rate: % of Tier 3 flags resolved within 48 hours"
  KPI definition (BACK-2.8 consumes this).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2 import Geography

from models import parking_locations, community_reports, conflicts

DEFAULT_MATCH_RADIUS_M = 15
DEFAULT_DECAY_WINDOW = timedelta(hours=48)


async def find_nearby_location(
    session: AsyncSession, lon: float, lat: float, radius_m: int = DEFAULT_MATCH_RADIUS_M
) -> dict[str, Any] | None:
    """Returns the closest existing parking_locations row within radius_m, or None."""
    point = cast(
        ST_SetSRID(ST_MakePoint(lon, lat), 4326),
        Geography(srid=4326),
    )

    stmt = (
        select(
            parking_locations.c.id,
            parking_locations.c.tier,
            parking_locations.c.status,
            parking_locations.c.restrictions,
        )
        .where(ST_DWithin(parking_locations.c.geom, point, radius_m))
        .limit(1)
    )

    result = await session.execute(stmt)
    row = result.first()
    return dict(row._mapping) if row else None


async def ingest_tier1(
    session: AsyncSession,
    lon: float,
    lat: float,
    status: str,
    restrictions: dict,
    municipal_feed_record_id: str,
) -> dict[str, Any]:
    """
    Tier 1 write path (municipal feed ingestion). Source data (Open311,
    permits, sweeping schedules) is parsed upstream by BACK-2.6's adapters
    before reaching this function — this function is source-agnostic.
    """
    existing = await find_nearby_location(session, lon, lat)
    now = datetime.now(timezone.utc)

    if existing is None:
        stmt = (
            insert(parking_locations)
            .values(
                geom=cast(ST_SetSRID(ST_MakePoint(lon, lat), 4326), Geography(srid=4326)),
                tier=1,
                status=status,
                restrictions=restrictions,
                last_verified_at=now,
                municipal_feed_record_id=municipal_feed_record_id,
                created_at=now,
                updated_at=now,
            )
            .returning(parking_locations.c.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return {"action": "created", "id": result.scalar_one(), "tier": 1}

    if existing["tier"] == 1:
        # Tier 1 vs. Tier 1: later municipal sync simply refreshes the baseline.
        await session.execute(
            update(parking_locations)
            .where(parking_locations.c.id == existing["id"])
            .values(
                status=status,
                restrictions=restrictions,
                last_verified_at=now,
                municipal_feed_record_id=municipal_feed_record_id,
                updated_at=now,
            )
        )
        await session.commit()
        return {"action": "updated", "id": existing["id"], "tier": 1}

    if existing["tier"] == 2:
        if existing["status"] == status:
            # Agreement: promote to Tier 1, municipal data now backs this pin.
            await session.execute(
                update(parking_locations)
                .where(parking_locations.c.id == existing["id"])
                .values(
                    tier=1,
                    status=status,
                    restrictions=restrictions,
                    last_verified_at=now,
                    municipal_feed_record_id=municipal_feed_record_id,
                    updated_at=now,
                )
            )
            await session.commit()
            return {"action": "promoted_to_tier1", "id": existing["id"], "tier": 1}
        else:
            # Disagreement: raise a conflict, do not overwrite.
            conflict_id = await _raise_conflict(
                session,
                location_id=existing["id"],
                tier1_snapshot={"status": status, "restrictions": restrictions, "source": "municipal_feed"},
                tier2_snapshot={"status": existing["status"], "restrictions": existing["restrictions"]},
            )
            return {"action": "conflict_raised", "id": existing["id"], "conflict_id": conflict_id, "tier": 3}

    if existing["tier"] == 3:
        # Already conflicted: refresh the Tier 1 side of the open conflict only.
        await _refresh_conflict_snapshot(
            session,
            location_id=existing["id"],
            side="tier1_snapshot",
            snapshot={"status": status, "restrictions": restrictions, "source": "municipal_feed"},
        )
        return {"action": "conflict_snapshot_refreshed", "id": existing["id"], "tier": 3}

    raise ValueError(f"Unexpected tier value: {existing['tier']}")


async def ingest_tier2(
    session: AsyncSession,
    user_id: str,
    lon: float,
    lat: float,
    status: str,
    restrictions: dict,
    photo_url: str | None = None,
    ai_extracted_fields: dict | None = None,
    confirmed_fields: dict | None = None,
    confidence_score: float | None = None,
) -> dict[str, Any]:
    """
    Tier 2 write path (community submissions). Expects fields already run
    through AI-3.4's confirmation step upstream (confirmed_fields holds the
    user-approved data; ai_extracted_fields is the raw AI output, kept for
    the AI-3.5 accuracy-tracking pipeline). This function itself does not
    call the AI pipeline — it's source-agnostic, same as ingest_tier1.
    """
    existing = await find_nearby_location(session, lon, lat)
    now = datetime.now(timezone.utc)

    if existing is None:
        location_stmt = (
            insert(parking_locations)
            .values(
                geom=cast(ST_SetSRID(ST_MakePoint(lon, lat), 4326), Geography(srid=4326)),
                tier=2,
                status=status,
                restrictions=restrictions,
                last_verified_at=now,
                created_at=now,
                updated_at=now,
            )
            .returning(parking_locations.c.id)
        )
        result = await session.execute(location_stmt)
        location_id = result.scalar_one()
        action = "created"

    elif existing["tier"] == 2:
        # Tier 2 vs. Tier 2: no Tier 1 baseline to conflict against.
        # Informal latest-wins; GAM-6.1's weighting is a later refinement.
        await session.execute(
            update(parking_locations)
            .where(parking_locations.c.id == existing["id"])
            .values(status=status, restrictions=restrictions, last_verified_at=now, updated_at=now)
        )
        location_id = existing["id"]
        action = "updated"

    elif existing["tier"] == 1:
        if existing["status"] == status:
            await session.execute(
                update(parking_locations)
                .where(parking_locations.c.id == existing["id"])
                .values(last_verified_at=now, updated_at=now)
            )
            location_id = existing["id"]
            action = "confirmed_tier1"
        else:
            conflict_id = await _raise_conflict(
                session,
                location_id=existing["id"],
                tier1_snapshot={"status": existing["status"], "restrictions": existing["restrictions"]},
                tier2_snapshot={"status": status, "restrictions": restrictions, "source": "community_report"},
            )
            await _insert_community_report(
                session, existing["id"], user_id, photo_url, ai_extracted_fields, confirmed_fields, confidence_score, now
            )
            await session.commit()
            return {"action": "conflict_raised", "id": existing["id"], "conflict_id": conflict_id, "tier": 3}

    elif existing["tier"] == 3:
        await _refresh_conflict_snapshot(
            session,
            location_id=existing["id"],
            side="tier2_snapshot",
            snapshot={"status": status, "restrictions": restrictions, "source": "community_report"},
        )
        location_id = existing["id"]
        action = "conflict_snapshot_refreshed"

    else:
        raise ValueError(f"Unexpected tier value: {existing['tier']}")

    await _insert_community_report(
        session, location_id, user_id, photo_url, ai_extracted_fields, confirmed_fields, confidence_score, now
    )
    await session.commit()
    return {"action": action, "id": location_id}


async def resolve_conflict(
    session: AsyncSession,
    conflict_id: str,
    resolution: str,
    resolved_by: str,
    resulting_status: str,
    resulting_restrictions: dict,
) -> dict[str, Any]:
    """
    Adjudication endpoint logic. Deliberate, explicit action only — never
    triggered automatically by ingest_tier1/ingest_tier2. Sets the location
    back to Tier 1 with the human-decided outcome (a resolved conflict
    always yields an authoritative answer, so Tier 1 is the correct
    resting state — matching the PRD's "no silent overwrite" requirement
    by making the overwrite here explicit and attributed).
    """
    now = datetime.now(timezone.utc)

    conflict_row = await session.execute(
        select(conflicts.c.parking_location_id).where(conflicts.c.id == conflict_id)
    )
    location_id = conflict_row.scalar_one()

    await session.execute(
        update(conflicts)
        .where(conflicts.c.id == conflict_id)
        .values(status="resolved", resolution=resolution, resolved_by=resolved_by, resolved_at=now)
    )

    await session.execute(
        update(parking_locations)
        .where(parking_locations.c.id == location_id)
        .values(
            tier=1,
            status=resulting_status,
            restrictions=resulting_restrictions,
            last_verified_at=now,
            updated_at=now,
        )
    )

    await session.commit()
    return {"action": "resolved", "conflict_id": conflict_id, "location_id": location_id}


# --- internal helpers -------------------------------------------------

async def _raise_conflict(
    session: AsyncSession, location_id: str, tier1_snapshot: dict, tier2_snapshot: dict
) -> str:
    now = datetime.now(timezone.utc)
    stmt = (
        insert(conflicts)
        .values(
            parking_location_id=location_id,
            tier1_snapshot=tier1_snapshot,
            tier2_snapshot=tier2_snapshot,
            status="open",
            opened_at=now,
            decay_deadline=now + DEFAULT_DECAY_WINDOW,
        )
        .returning(conflicts.c.id)
    )
    result = await session.execute(stmt)
    conflict_id = result.scalar_one()

    await session.execute(
        update(parking_locations)
        .where(parking_locations.c.id == location_id)
        .values(tier=3, updated_at=now)
    )
    await session.commit()
    return conflict_id


async def _refresh_conflict_snapshot(
    session: AsyncSession, location_id: str, side: str, snapshot: dict
) -> None:
    """side is 'tier1_snapshot' or 'tier2_snapshot'."""
    open_conflict = await session.execute(
        select(conflicts.c.id)
        .where(conflicts.c.parking_location_id == location_id, conflicts.c.status == "open")
        .limit(1)
    )
    conflict_id = open_conflict.scalar_one_or_none()
    if conflict_id is None:
        # Defensive: tier==3 with no open conflict shouldn't happen, but
        # don't silently swallow it if it does.
        raise ValueError(f"parking_location {location_id} is Tier 3 but has no open conflict")

    await session.execute(
        update(conflicts).where(conflicts.c.id == conflict_id).values(**{side: snapshot})
    )
    await session.commit()


async def _insert_community_report(
    session: AsyncSession,
    location_id: str,
    user_id: str,
    photo_url: str | None,
    ai_extracted_fields: dict | None,
    confirmed_fields: dict | None,
    confidence_score: float | None,
    now: datetime,
) -> None:
    await session.execute(
        insert(community_reports).values(
            parking_location_id=location_id,
            user_id=user_id,
            photo_url=photo_url,
            ai_extracted_fields=ai_extracted_fields,
            confirmed_fields=confirmed_fields or {},
            confidence_score=confidence_score,
            created_at=now,
        )
    )