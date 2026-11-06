import os
import uuid

import pytest_asyncio

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

_TRUNCATE = """
truncate conflict_votes, conflicts, community_reports,
         municipal_feed_records, parking_locations cascade;
truncate auth.users cascade;
update engine_settings set
  point_match_radius_m = 15,
  segment_snap_radius_m = 20,
  conflict_decay_window = interval '48 hours',
  quorum_min_votes = 3,
  quorum_margin = 0.75,
  cluster_cell_px = 64;
"""


@pytest_asyncio.fixture
async def engine():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    eng = create_async_engine(url, poolclass=NullPool)
    async with eng.begin() as conn:
        for statement in filter(None, (s.strip() for s in _TRUNCATE.split(";"))):
            await conn.execute(text(statement))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def make_user(engine):
    from sqlalchemy import text

    async def _make() -> str:
        user_id = str(uuid.uuid4())
        async with engine.begin() as conn:
            await conn.execute(text("insert into auth.users (id) values (CAST(:id AS uuid))"), {"id": user_id})
        return user_id

    return _make
