"""
Integration tests for WP-2a against real PostGIS (see conftest.requires_db).

Geometry used throughout: a ~85 m stretch of street running west -> east at
lat 40.75. North of it is the LEFT curb, south is the RIGHT curb.
1e-5 deg lat ~= 1.1 m.
"""

import asyncio
import os

import pytest
from sqlalchemy import func, select, text

from models import community_reports, conflicts, parking_locations
from services.ingestion import (
    ConflictNotOpen,
    cast_conflict_vote,
    ingest_tier1,
    ingest_tier2,
    resolve_conflict,
)
from services.parking import get_pin_detail, get_pins_in_bbox

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set (needs PostGIS with shim + migrations; see `make test-db`)",
)

LAT = 40.75
WEST, EAST = -73.9900, -73.9890
MID_LON = (WEST + EAST) / 2
STREET = {"type": "LineString", "coordinates": [[WEST, LAT], [EAST, LAT]]}
STREET_REVERSED = {"type": "LineString", "coordinates": [[EAST, LAT], [WEST, LAT]]}
NORTH = LAT + 0.00005  # ~5.5 m north of centerline -> left curb
SOUTH = LAT - 0.00005  # ~5.5 m south -> right curb
BBOX = (WEST - 0.001, LAT - 0.001, EAST + 0.001, LAT + 0.001)


async def _segment(session, side: str, status: str, external_id: str, geometry=STREET) -> str:
    result = await ingest_tier1(
        session,
        source_type="permit",
        external_id=external_id,
        payload={},
        geometry=geometry,
        status=status,
        restrictions={},
        curb_side=side,
        street_name="Test St",
    )
    return str(result["id"])


async def _report(session, user_id: str, lat: float, status: str, lon: float = MID_LON) -> dict:
    return await ingest_tier2(session, user_id=user_id, lon=lon, lat=lat, status=status, restrictions={})


async def _count(session, table, *where) -> int:
    return await session.scalar(select(func.count()).select_from(table).where(*where))


async def test_curb_side_of(session):
    line = "ST_GeomFromText('LINESTRING(0 0, 10 0)', 4326)"
    left = await session.scalar(text(f"select curb_side_of({line}, ST_SetSRID(ST_MakePoint(5, 1), 4326))"))
    right = await session.scalar(text(f"select curb_side_of({line}, ST_SetSRID(ST_MakePoint(5, -1), 4326))"))
    assert (left, right) == ("left", "right")


async def test_viewport_returns_all_geometry_kinds_without_error(session):
    await _segment(session, "left", "available", "seg-1")
    await ingest_tier1(
        session, source_type="permit", external_id="pt-1", payload={},
        geometry={"type": "Point", "coordinates": [WEST, LAT + 0.0005]},
        status="restricted", restrictions={},
    )
    await ingest_tier1(
        session, source_type="permit", external_id="lot-1", payload={},
        geometry={"type": "Polygon", "coordinates": [[
            [WEST, LAT - 0.0008], [WEST + 0.0003, LAT - 0.0008],
            [WEST + 0.0003, LAT - 0.0005], [WEST, LAT - 0.0005], [WEST, LAT - 0.0008],
        ]]},
        status="conditional", restrictions={},
    )

    pins = await get_pins_in_bbox(session, *BBOX)

    assert sorted(p["kind"] for p in pins) == ["lot", "point", "segment"]
    segment = next(p for p in pins if p["kind"] == "segment")
    assert segment["anchor_lon"] == pytest.approx(MID_LON, abs=1e-6)
    assert segment["geometry"]["type"] == "LineString"
    assert segment["curb_side"] == "left"


async def test_report_snaps_to_segment_on_same_side(session, make_user):
    user = await make_user()
    left_id = await _segment(session, "left", "available", "seg-left")
    right_id = await _segment(session, "right", "available", "seg-right")

    north = await _report(session, user, NORTH, "available")
    south = await _report(session, user, SOUTH, "available")

    assert str(north["id"]) == left_id
    assert str(south["id"]) == right_id
    assert north["action"] == south["action"] == "confirmed_tier1"
    assert await _count(session, parking_locations) == 2


async def test_report_without_match_creates_point_then_reuses_it(session, make_user):
    user = await make_user()
    far_lat = LAT + 0.01  # nowhere near the street

    first = await _report(session, user, far_lat, "available")
    second = await _report(session, user, far_lat + 0.00004, "restricted")  # ~4.4 m away

    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert second["id"] == first["id"]
    assert await _count(session, parking_locations) == 1


async def test_concurrent_reports_create_one_location(session_factory, make_user):
    users = [await make_user(), await make_user()]
    far_lat = LAT + 0.02

    async def submit(user_id):
        async with session_factory() as s:
            return await _report(s, user_id, far_lat, "available")

    results = await asyncio.gather(*(submit(u) for u in users))

    assert {r["id"] for r in results} == {results[0]["id"]}
    async with session_factory() as s:
        assert await _count(s, parking_locations) == 1
        assert await _count(s, community_reports) == 2


async def test_disagreement_raises_exactly_one_conflict(session, make_user):
    a, b = await make_user(), await make_user()
    seg_id = await _segment(session, "left", "restricted", "seg-1")

    first = await _report(session, a, NORTH, "available")
    second = await _report(session, b, NORTH, "available")

    assert first["action"] == "conflict_raised"
    assert second["action"] == "conflict_snapshot_refreshed"
    assert await _count(session, conflicts, conflicts.c.status == "open") == 1
    detail = await get_pin_detail(session, seg_id)
    assert detail["tier"] == 3
    assert detail["open_conflict"]["tier2_snapshot"]["status"] == "available"
    assert len(detail["reviews"]) == 2
    assert all("user_id" not in r for r in detail["reviews"])


async def _open_conflict(session, make_user) -> tuple[str, str]:
    seg_id = await _segment(session, "left", "restricted", "seg-1")
    result = await _report(session, await make_user(), NORTH, "available")
    return seg_id, str(result["conflict_id"])


async def test_quorum_resolves_to_community_side(session, make_user):
    seg_id, conflict_id = await _open_conflict(session, make_user)

    outcomes = [
        await cast_conflict_vote(session, conflict_id=conflict_id, user_id=await make_user(), supports="tier2")
        for _ in range(3)
    ]

    assert [o["action"] for o in outcomes] == ["vote_recorded", "vote_recorded", "resolved"]
    assert outcomes[-1]["winner"] == "tier2"
    detail = await get_pin_detail(session, seg_id)
    assert (detail["tier"], detail["status"], detail["open_conflict"]) == (1, "available", None)

    with pytest.raises(ConflictNotOpen):
        await cast_conflict_vote(session, conflict_id=conflict_id, user_id=await make_user(), supports="tier1")


async def test_split_vote_below_margin_stays_open(session, make_user):
    _, conflict_id = await _open_conflict(session, make_user)

    for side in ["tier2", "tier1", "tier2", "tier1", "tier2"]:  # 3 vs 2 = 60% < 75%
        outcome = await cast_conflict_vote(session, conflict_id=conflict_id, user_id=await make_user(), supports=side)

    assert outcome["action"] == "vote_recorded"
    assert outcome["tally"] == {"tier1": 2, "tier2": 3, "unsure": 0}


async def test_unsure_and_changed_votes(session, make_user):
    _, conflict_id = await _open_conflict(session, make_user)
    voter = await make_user()

    await cast_conflict_vote(session, conflict_id=conflict_id, user_id=voter, supports="tier1")
    outcome = await cast_conflict_vote(session, conflict_id=conflict_id, user_id=voter, supports="unsure")

    assert outcome["tally"] == {"tier1": 0, "tier2": 0, "unsure": 1}


async def test_reversed_feed_segment_matches_same_curb(session):
    first = await _segment(session, "left", "available", "feed-a")
    # Same physical curb (north side), digitized east -> west: now it's the RIGHT side.
    second = await _segment(session, "right", "restricted", "feed-b", geometry=STREET_REVERSED)

    assert second == first
    assert await _count(session, parking_locations) == 1


async def _resolve_for_community(session, make_user) -> str:
    """Feed says restricted, community says available, quorum sides with community."""
    seg_id, conflict_id = await _open_conflict(session, make_user)
    for _ in range(3):
        await cast_conflict_vote(session, conflict_id=conflict_id, user_id=await make_user(), supports="tier2")
    return seg_id


async def test_unchanged_feed_resync_keeps_community_resolution(session, make_user):
    seg_id = await _resolve_for_community(session, make_user)

    resync = await _segment(session, "left", "restricted", "seg-1")  # same feed record, same claim
    detail = await get_pin_detail(session, seg_id)

    assert resync == seg_id
    assert (detail["tier"], detail["status"], detail["open_conflict"]) == (1, "available", None)


async def test_feed_agreeing_with_resolution_then_changing_is_a_normal_update(session, make_user):
    seg_id = await _resolve_for_community(session, make_user)

    await _segment(session, "left", "available", "seg-1")  # city now agrees
    await _segment(session, "left", "restricted", "seg-1")  # later genuine rule change
    detail = await get_pin_detail(session, seg_id)

    assert (detail["tier"], detail["status"], detail["open_conflict"]) == (1, "restricted", None)


async def test_changed_feed_rule_against_resolution_reopens_conflict(session, make_user):
    seg_id = await _resolve_for_community(session, make_user)

    result = await ingest_tier1(
        session, source_type="permit", external_id="seg-1", payload={}, geometry=STREET,
        status="conditional", restrictions={"max_hours": 2}, curb_side="left", street_name="Test St",
    )
    detail = await get_pin_detail(session, seg_id)

    assert result["action"] == "conflict_raised"
    assert detail["tier"] == 3
    assert detail["status"] == "available"  # resolved answer stays visible until re-resolved
    assert detail["open_conflict"]["tier1_snapshot"]["status"] == "conditional"
    assert detail["open_conflict"]["tier2_snapshot"]["status"] == "available"
    assert await _count(session, conflicts, conflicts.c.status == "open") == 1


async def test_unchanged_feed_resync_keeps_ops_override(session, make_user):
    seg_id, conflict_id = await _open_conflict(session, make_user)
    await resolve_conflict(
        session, conflict_id=conflict_id, resolution="sign photographed by ops",
        resolved_by=await make_user(), resulting_status="conditional", resulting_restrictions={"max_hours": 2},
    )

    await _segment(session, "left", "restricted", "seg-1")
    detail = await get_pin_detail(session, seg_id)

    assert (detail["tier"], detail["status"], detail["restrictions"]) == (1, "conditional", {"max_hours": 2})
