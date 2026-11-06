"""
Integration tests for server-side clustering (pin_clusters, GET /pins/clusters).

At zoom 10 with 64 px cells a cell is ~4.9 km wide, so everything within a
few hundred metres of BASE lands in one cell; FAR is ~50 km away.
Pins are spaced >= ~55 m apart so the 15 m report matcher never merges them.
"""

import os

import pytest
from fastapi.testclient import TestClient

from db import get_db_session
from main import app
from services.ingestion import ingest_tier1, ingest_tier2
from services.parking import get_pin_clusters

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set (needs PostGIS with shim + migrations; see `make test-db`)",
)

ZOOM = 10
BASE_LON, BASE_LAT = -73.99, 40.75
STEP = 0.0005  # ~55 m of latitude
FAR_LAT = BASE_LAT + 0.45  # ~50 km north
WIDE = (BASE_LON - 1, BASE_LAT - 1, BASE_LON + 1, BASE_LAT + 1)


async def _tier1_point(session, n: int, status: str, lat: float = BASE_LAT) -> str:
    r = await ingest_tier1(
        session, source_type="permit", external_id=f"pt-{n}-{lat}", payload={},
        geometry={"type": "Point", "coordinates": [BASE_LON, lat + n * STEP]},
        status=status, restrictions={},
    )
    return str(r["id"])


async def _tier2_point(session, user: str, n: int, status: str, lat: float = BASE_LAT) -> str:
    r = await ingest_tier2(session, user_id=user, lon=BASE_LON, lat=lat + n * STEP, status=status, restrictions={})
    return str(r["id"])


async def _tier3_point(session, user: str, n: int) -> str:
    loc = await _tier1_point(session, n, "restricted")
    r = await ingest_tier2(session, user_id=user, lon=BASE_LON, lat=BASE_LAT + n * STEP, status="available",
                           restrictions={})
    assert r["action"] == "conflict_raised"
    return loc


async def _clusters(session, bbox=WIDE, zoom=ZOOM):
    return await get_pin_clusters(session, *bbox, zoom)


async def test_representatives_and_counts_per_filter(session, make_user):
    user = await make_user()
    t2_free = await _tier2_point(session, user, 0, "available")  # newest, but Tier 2
    t1_restricted = await _tier1_point(session, 1, "restricted")
    t3 = await _tier3_point(session, user, 2)
    t1_free = await _tier1_point(session, 3, "available")

    [cluster] = await _clusters(session)

    assert cluster["counts"] == {"all": 4, "verified": 2, "free": 2}
    reps = cluster["representatives"]
    assert reps["all"]["id"] == t3  # Tier 3 outranks everything
    assert reps["verified"]["tier"] == 1
    assert reps["verified"]["id"] in {t1_restricted, t1_free}
    assert reps["free"]["id"] == t1_free  # Tier 1 outranks the newer Tier 2
    assert t2_free not in {r["id"] for r in reps.values()}


async def test_filter_with_no_members_has_no_representative(session, make_user):
    user = await make_user()
    await _tier2_point(session, user, 0, "restricted")

    [cluster] = await _clusters(session)

    assert cluster["counts"] == {"all": 1, "verified": 0, "free": 0}
    assert cluster["representatives"]["all"]["tier"] == 2
    assert cluster["representatives"]["verified"] is None
    assert cluster["representatives"]["free"] is None


async def test_far_apart_pins_form_separate_clusters(session):
    await _tier1_point(session, 0, "available")
    await _tier1_point(session, 0, "available", lat=FAR_LAT)

    clusters = await _clusters(session)

    assert len(clusters) == 2
    assert all(c["counts"]["all"] == 1 for c in clusters)


async def test_segment_is_clustered_by_its_midpoint(session):
    await ingest_tier1(
        session, source_type="permit", external_id="seg", payload={},
        geometry={"type": "LineString", "coordinates": [[BASE_LON, BASE_LAT], [BASE_LON + 0.001, BASE_LAT]]},
        status="conditional", restrictions={}, curb_side="left",
    )

    [cluster] = await _clusters(session)

    assert cluster["representatives"]["all"]["kind"] == "segment"
    assert cluster["representatives"]["all"]["anchor_lon"] == pytest.approx(BASE_LON + 0.0005, abs=1e-6)


async def test_edge_cell_counts_members_outside_the_viewport(session):
    await _tier1_point(session, 0, "available")
    await _tier1_point(session, 1, "available")  # ~55 m north of the first
    [whole] = await _clusters(session)
    assert whole["counts"]["all"] == 2

    # Viewport ends between the two pins; the shared cell still counts both.
    cut = (BASE_LON - 0.01, BASE_LAT - 0.01, BASE_LON + 0.01, BASE_LAT + STEP / 2)
    [edge] = await _clusters(session, bbox=cut)

    assert edge["cell"] == whole["cell"]
    assert edge["counts"]["all"] == 2


async def test_cell_ids_are_stable_across_viewports(session):
    await _tier1_point(session, 0, "available")

    [a] = await _clusters(session, bbox=WIDE)
    [b] = await _clusters(session, bbox=(BASE_LON - 0.02, BASE_LAT - 0.02, BASE_LON + 0.05, BASE_LAT + 0.03))

    assert a["cell"] == b["cell"]
    assert a["cell"].startswith(f"{ZOOM}/")


async def test_higher_zoom_splits_clusters(session):
    await _tier1_point(session, 0, "available")
    await _tier1_point(session, 4, "available")  # ~220 m apart

    assert len(await _clusters(session, zoom=10)) == 1
    assert len(await _clusters(session, zoom=13)) == 2  # ~600 m cells


# --- route ---------------------------------------------------------------


@pytest.fixture
def client(session_factory):
    async def _session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


PHONE_VIEW = (BASE_LON - 0.3, BASE_LAT - 0.5, BASE_LON + 0.3, BASE_LAT + 0.5)  # ~z10 viewport


def _params(**overrides):
    params = dict(zip(("min_lon", "min_lat", "max_lon", "max_lat"), PHONE_VIEW), zoom=ZOOM)
    params.update(overrides)
    return params


async def test_route_returns_clusters(client, session):
    await _tier1_point(session, 0, "available")

    response = client.get("/pins/clusters", params=_params())

    assert response.status_code == 200
    body = response.json()
    assert (body["zoom"], body["raw_min_zoom"]) == (ZOOM, 14)
    assert body["clusters"][0]["counts"] == {"all": 1, "verified": 1, "free": 1}


def test_route_rejects_street_zoom(client):
    assert client.get("/pins/clusters", params=_params(zoom=14)).status_code == 422


def test_route_rejects_oversized_bbox(client):
    response = client.get("/pins/clusters", params=_params(zoom=13))  # z10-sized view at z13
    assert response.status_code == 400
