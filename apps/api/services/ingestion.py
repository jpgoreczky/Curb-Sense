"""
BACK-2.3: Three-tier data ingestion and conflict resolution engine.

Rules:
- Every public function here is one unit of work: one transaction, one commit,
  full rollback on any error. Helpers never commit.
- Spatial matching lives in PostGIS (match_location_for_report,
  match_location_for_feed, curb_side_of, lock_area). Python only orchestrates.
- Community reports snap to a curb segment on the same side of the street
  (segment_snap_radius_m), else to the nearest point/lot (point_match_radius_m),
  else create a new Tier 2 point.
- Concurrent reports that could create a location in the same area are
  serialized with lock_area(); the matched location row is locked FOR UPDATE.
- Tier 3 is never silently overwritten. A conflict resolves only by community
  quorum (cast_conflict_vote) or an explicit ops override (resolve_conflict).
- Radii, decay window and quorum rules come from the engine_settings row.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import Text, cast, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    community_reports,
    conflict_votes,
    conflicts,
    engine_settings,
    municipal_feed_records,
    parking_locations,
)

SEGMENT_TYPES = {"LineString"}
ALLOWED_TIER1_TYPES = {"Point", "LineString", "Polygon"}


class ConflictNotFound(Exception):
    pass


class ConflictNotOpen(Exception):
    pass


@dataclass(frozen=True)
class EngineSettings:
    point_match_radius_m: float
    segment_snap_radius_m: float
    conflict_decay_window: timedelta
    quorum_min_votes: int
    quorum_margin: float


# --- unit of work / shared helpers -------------------------------------------


@asynccontextmanager
async def _unit_of_work(session: AsyncSession) -> AsyncIterator[None]:
    try:
        yield
        await session.commit()
    except BaseException:
        await session.rollback()
        raise


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def load_engine_settings(session: AsyncSession) -> EngineSettings:
    row = (await session.execute(select(engine_settings).where(engine_settings.c.id.is_(True)))).one()
    return EngineSettings(
        point_match_radius_m=float(row.point_match_radius_m),
        segment_snap_radius_m=float(row.segment_snap_radius_m),
        conflict_decay_window=row.conflict_decay_window,
        quorum_min_votes=int(row.quorum_min_votes),
        quorum_margin=float(row.quorum_margin),
    )


def _point_geog(lon: float, lat: float):
    return cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography(srid=4326))


def _geojson_geog(geometry: dict):
    return cast(
        func.ST_SetSRID(func.ST_GeomFromGeoJSON(cast(json.dumps(geometry), Text)), 4326),
        Geography(srid=4326),
    )


_POINT_SQL = "ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision), CAST(:lat AS double precision)), 4326)::geography"


async def _lock_location(session: AsyncSession, location_id: Any) -> dict[str, Any] | None:
    row = (
        await session.execute(
            select(
                parking_locations.c.id,
                parking_locations.c.tier,
                parking_locations.c.status,
                parking_locations.c.restrictions,
            )
            .where(parking_locations.c.id == location_id)
            .with_for_update()
        )
    ).first()
    return dict(row._mapping) if row else None


def validate_tier1_geometry(geometry: dict, curb_side: str | None) -> None:
    gtype = geometry.get("type")
    if gtype not in ALLOWED_TIER1_TYPES:
        raise ValueError(f"Unsupported geometry type: {gtype}")
    if (gtype in SEGMENT_TYPES) != (curb_side is not None):
        raise ValueError("curb_side is required for LineString segments and forbidden otherwise")
    if curb_side is not None and curb_side not in ("left", "right"):
        raise ValueError("curb_side must be 'left' or 'right'")


# --- Tier 1: municipal feeds --------------------------------------------------


async def ingest_tier1(
    session: AsyncSession,
    *,
    source_type: str,
    external_id: str,
    payload: dict,
    geometry: dict,
    status: str,
    restrictions: dict,
    curb_side: str | None = None,
    street_name: str | None = None,
    from_street: str | None = None,
    to_street: str | None = None,
    osm_way_id: int | None = None,
) -> dict[str, Any]:
    """
    Tier 1 write path. BACK-2.6 adapters parse their feed into a GeoJSON
    geometry (Point | LineString + curb_side | Polygon) and call this.
    Location lookup: the feed record's existing link first, then spatial match.
    Feeds run as single-writer batch jobs; duplicate feed rows are prevented
    by uq_source_external, so no area lock is taken here.
    """
    validate_tier1_geometry(geometry, curb_side)
    geog = _geojson_geog(geometry)
    descriptive = {
        "curb_side": curb_side,
        "street_name": street_name,
        "from_street": from_street,
        "to_street": to_street,
        "osm_way_id": osm_way_id,
    }

    async with _unit_of_work(session):
        now = _now()

        feed_stmt = (
            pg_insert(municipal_feed_records)
            .values(source_type=source_type, external_id=external_id, payload=payload, synced_at=now)
            .on_conflict_do_update(
                constraint="uq_source_external",
                set_={"payload": payload, "synced_at": now},
            )
            .returning(municipal_feed_records.c.id, municipal_feed_records.c.parking_location_id)
        )
        feed_row = (await session.execute(feed_stmt)).one()
        feed_id = feed_row.id

        existing = None
        if feed_row.parking_location_id is not None:
            existing = await _lock_location(session, feed_row.parking_location_id)
        if existing is None:
            matched_id = await session.scalar(
                text(
                    "select match_location_for_feed("
                    "ST_SetSRID(ST_GeomFromGeoJSON(CAST(:g AS text)), 4326)::geography, "
                    "CAST(:side AS text))"
                ),
                {"g": json.dumps(geometry), "side": curb_side},
            )
            if matched_id is not None:
                existing = await _lock_location(session, matched_id)

        if existing is None:
            location_id = (
                await session.execute(
                    insert(parking_locations)
                    .values(
                        geom=geog,
                        tier=1,
                        status=status,
                        restrictions=restrictions,
                        last_verified_at=now,
                        municipal_feed_record_id=feed_id,
                        created_at=now,
                        updated_at=now,
                        **descriptive,
                    )
                    .returning(parking_locations.c.id)
                )
            ).scalar_one()
            result = {"action": "created", "id": location_id, "tier": 1}

        elif existing["tier"] == 1:
            # Later municipal sync refreshes the baseline, geometry included.
            location_id = existing["id"]
            await session.execute(
                update(parking_locations)
                .where(parking_locations.c.id == location_id)
                .values(
                    geom=geog,
                    status=status,
                    restrictions=restrictions,
                    last_verified_at=now,
                    municipal_feed_record_id=feed_id,
                    updated_at=now,
                    **descriptive,
                )
            )
            result = {"action": "updated", "id": location_id, "tier": 1}

        elif existing["tier"] == 2:
            location_id = existing["id"]
            if existing["status"] == status:
                await session.execute(
                    update(parking_locations)
                    .where(parking_locations.c.id == location_id)
                    .values(
                        tier=1,
                        restrictions=restrictions,
                        last_verified_at=now,
                        municipal_feed_record_id=feed_id,
                        updated_at=now,
                    )
                )
                result = {"action": "promoted_to_tier1", "id": location_id, "tier": 1}
            else:
                conflict_id = await _raise_conflict(
                    session,
                    location_id=location_id,
                    tier1_snapshot={"status": status, "restrictions": restrictions, "source": "municipal_feed"},
                    tier2_snapshot={"status": existing["status"], "restrictions": existing["restrictions"]},
                    now=now,
                )
                result = {"action": "conflict_raised", "id": location_id, "conflict_id": conflict_id, "tier": 3}

        elif existing["tier"] == 3:
            location_id = existing["id"]
            await _refresh_conflict_snapshot(
                session,
                location_id=location_id,
                side="tier1_snapshot",
                snapshot={"status": status, "restrictions": restrictions, "source": "municipal_feed"},
            )
            result = {"action": "conflict_snapshot_refreshed", "id": location_id, "tier": 3}

        else:
            raise ValueError(f"Unexpected tier value: {existing['tier']}")

        await session.execute(
            update(municipal_feed_records)
            .where(municipal_feed_records.c.id == feed_id)
            .values(parking_location_id=location_id)
        )

    return result


# --- Tier 2: community reports -----------------------------------------------


async def ingest_tier2(
    session: AsyncSession,
    *,
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
    Tier 2 write path. confirmed_fields is the user-approved data from the
    AI-3.4 confirmation step; ai_extracted_fields is raw model output kept
    for AI-3.5 accuracy tracking. Reports are always points (where the photo
    was taken); the database decides whether they land on a segment.
    """
    async with _unit_of_work(session):
        settings = await load_engine_settings(session)
        now = _now()
        params = {"lon": lon, "lat": lat}

        await session.execute(
            text(f"select lock_area({_POINT_SQL}, CAST(:r AS double precision))"),
            {**params, "r": settings.point_match_radius_m},
        )
        matched_id = await session.scalar(text(f"select match_location_for_report({_POINT_SQL})"), params)
        existing = await _lock_location(session, matched_id) if matched_id is not None else None

        if existing is None:
            location_id = (
                await session.execute(
                    insert(parking_locations)
                    .values(
                        geom=_point_geog(lon, lat),
                        tier=2,
                        status=status,
                        restrictions=restrictions,
                        last_verified_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                    .returning(parking_locations.c.id)
                )
            ).scalar_one()
            result: dict[str, Any] = {"action": "created", "id": location_id, "tier": 2}

        elif existing["tier"] == 2:
            # No Tier 1 baseline to conflict against: latest wins (GAM-6.1
            # contributor weighting is a later refinement).
            location_id = existing["id"]
            await session.execute(
                update(parking_locations)
                .where(parking_locations.c.id == location_id)
                .values(status=status, restrictions=restrictions, last_verified_at=now, updated_at=now)
            )
            result = {"action": "updated", "id": location_id, "tier": 2}

        elif existing["tier"] == 1:
            location_id = existing["id"]
            if existing["status"] == status:
                await session.execute(
                    update(parking_locations)
                    .where(parking_locations.c.id == location_id)
                    .values(last_verified_at=now, updated_at=now)
                )
                result = {"action": "confirmed_tier1", "id": location_id, "tier": 1}
            else:
                conflict_id = await _raise_conflict(
                    session,
                    location_id=location_id,
                    tier1_snapshot={"status": existing["status"], "restrictions": existing["restrictions"]},
                    tier2_snapshot={"status": status, "restrictions": restrictions, "source": "community_report"},
                    now=now,
                )
                result = {"action": "conflict_raised", "id": location_id, "conflict_id": conflict_id, "tier": 3}

        elif existing["tier"] == 3:
            location_id = existing["id"]
            await _refresh_conflict_snapshot(
                session,
                location_id=location_id,
                side="tier2_snapshot",
                snapshot={"status": status, "restrictions": restrictions, "source": "community_report"},
            )
            result = {"action": "conflict_snapshot_refreshed", "id": location_id, "tier": 3}

        else:
            raise ValueError(f"Unexpected tier value: {existing['tier']}")

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

    return result


# --- Tier 3: voting and ops override -----------------------------------------


async def cast_conflict_vote(
    session: AsyncSession,
    *,
    conflict_id: str,
    user_id: str,
    supports: str,
) -> dict[str, Any]:
    """
    Record (or change) a user's vote on an open conflict. 'unsure' votes are
    stored but don't count. The conflict resolves to the leading side once it
    has >= quorum_min_votes AND >= quorum_margin of the decided votes.
    """
    if supports not in ("tier1", "tier2", "unsure"):
        raise ValueError("supports must be 'tier1', 'tier2' or 'unsure'")

    async with _unit_of_work(session):
        settings = await load_engine_settings(session)
        conflict = await _lock_open_conflict(session, conflict_id)
        now = _now()

        await session.execute(
            pg_insert(conflict_votes)
            .values(conflict_id=conflict_id, user_id=user_id, supports=supports, created_at=now)
            .on_conflict_do_update(
                index_elements=[conflict_votes.c.conflict_id, conflict_votes.c.user_id],
                set_={"supports": supports, "created_at": now},
            )
        )

        tally_rows = await session.execute(
            select(conflict_votes.c.supports, func.count())
            .where(conflict_votes.c.conflict_id == conflict_id)
            .group_by(conflict_votes.c.supports)
        )
        tally = {"tier1": 0, "tier2": 0, "unsure": 0}
        for side, count in tally_rows:
            tally[side] = int(count)

        winner = _quorum_winner(tally["tier1"], tally["tier2"], settings)
        if winner is None:
            return {"action": "vote_recorded", "conflict_id": conflict_id, "tally": tally}

        snapshot = conflict["tier1_snapshot"] if winner == "tier1" else conflict["tier2_snapshot"]
        await _apply_resolution(
            session,
            conflict_id=conflict_id,
            location_id=conflict["parking_location_id"],
            resolution=f"community_quorum:{winner}",
            resolution_source="community_quorum",
            resolved_by=None,
            resulting_status=snapshot["status"],
            resulting_restrictions=snapshot.get("restrictions") or {},
            now=now,
        )

    return {"action": "resolved", "conflict_id": conflict_id, "winner": winner, "tally": tally}


def _quorum_winner(tier1_votes: int, tier2_votes: int, settings: EngineSettings) -> str | None:
    decided = tier1_votes + tier2_votes
    if decided == 0 or tier1_votes == tier2_votes:
        return None
    leader, lead_votes = ("tier1", tier1_votes) if tier1_votes > tier2_votes else ("tier2", tier2_votes)
    if lead_votes >= settings.quorum_min_votes and lead_votes / decided >= settings.quorum_margin:
        return leader
    return None


async def resolve_conflict(
    session: AsyncSession,
    *,
    conflict_id: str,
    resolution: str,
    resolved_by: str,
    resulting_status: str,
    resulting_restrictions: dict,
) -> dict[str, Any]:
    """Ops-only override (route requires the ops role). Explicit and attributed."""
    async with _unit_of_work(session):
        conflict = await _lock_open_conflict(session, conflict_id)
        await _apply_resolution(
            session,
            conflict_id=conflict_id,
            location_id=conflict["parking_location_id"],
            resolution=resolution,
            resolution_source="ops_override",
            resolved_by=resolved_by,
            resulting_status=resulting_status,
            resulting_restrictions=resulting_restrictions,
            now=_now(),
        )
        location_id = conflict["parking_location_id"]

    return {"action": "resolved", "conflict_id": conflict_id, "location_id": location_id}


# --- internal helpers (never commit) -----------------------------------------


async def _lock_open_conflict(session: AsyncSession, conflict_id: str) -> dict[str, Any]:
    row = (
        await session.execute(
            select(
                conflicts.c.id,
                conflicts.c.parking_location_id,
                conflicts.c.status,
                conflicts.c.tier1_snapshot,
                conflicts.c.tier2_snapshot,
            )
            .where(conflicts.c.id == conflict_id)
            .with_for_update()
        )
    ).first()
    if row is None:
        raise ConflictNotFound(conflict_id)
    if row.status != "open":
        raise ConflictNotOpen(conflict_id)
    return dict(row._mapping)


async def _apply_resolution(
    session: AsyncSession,
    *,
    conflict_id: str,
    location_id: Any,
    resolution: str,
    resolution_source: str,
    resolved_by: str | None,
    resulting_status: str,
    resulting_restrictions: dict,
    now: datetime,
) -> None:
    await session.execute(
        update(conflicts)
        .where(conflicts.c.id == conflict_id)
        .values(
            status="resolved",
            resolution=resolution,
            resolution_source=resolution_source,
            resolved_by=resolved_by,
            resolved_at=now,
        )
    )
    # A resolved conflict yields an authoritative answer, so Tier 1 is the
    # resting state. This is the only place Tier 3 data is overwritten.
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


async def _raise_conflict(
    session: AsyncSession,
    *,
    location_id: Any,
    tier1_snapshot: dict,
    tier2_snapshot: dict,
    now: datetime,
) -> Any:
    settings = await load_engine_settings(session)
    conflict_id = (
        await session.execute(
            insert(conflicts)
            .values(
                parking_location_id=location_id,
                tier1_snapshot=tier1_snapshot,
                tier2_snapshot=tier2_snapshot,
                status="open",
                opened_at=now,
                decay_deadline=now + settings.conflict_decay_window,
            )
            .returning(conflicts.c.id)
        )
    ).scalar_one()
    await session.execute(
        update(parking_locations)
        .where(parking_locations.c.id == location_id)
        .values(tier=3, updated_at=now)
    )
    return conflict_id


async def _refresh_conflict_snapshot(
    session: AsyncSession, *, location_id: Any, side: str, snapshot: dict
) -> None:
    """side is 'tier1_snapshot' or 'tier2_snapshot'."""
    conflict_id = await session.scalar(
        select(conflicts.c.id)
        .where(conflicts.c.parking_location_id == location_id, conflicts.c.status == "open")
        .with_for_update()
    )
    if conflict_id is None:
        raise ValueError(f"parking_location {location_id} is Tier 3 but has no open conflict")
    await session.execute(update(conflicts).where(conflicts.c.id == conflict_id).values(**{side: snapshot}))
