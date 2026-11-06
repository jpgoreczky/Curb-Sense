from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    Interval,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

parking_locations = Table(
    "parking_locations",
    metadata,
    Column("id", UUID),
    Column("geom", Geography(srid=4326)),
    Column("curb_side", String),
    Column("street_name", String),
    Column("from_street", String),
    Column("to_street", String),
    Column("osm_way_id", BigInteger),
    Column("tier", SmallInteger),
    Column("status", String),
    Column("restrictions", JSONB),
    Column("last_verified_at", DateTime(timezone=True)),
    Column("municipal_feed_record_id", UUID),
    Column("display_priority", SmallInteger),  # generated, read-only
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

# Read-only view (see migration 20261106050000). Anchors + GeoJSON computed in PostGIS.
pin_features = Table(
    "pin_features",
    metadata,
    Column("id", UUID),
    Column("kind", String),
    Column("anchor_lon", Float),
    Column("anchor_lat", Float),
    Column("geometry", JSONB),
    Column("geom", Geography(srid=4326)),
    Column("curb_side", String),
    Column("tier", SmallInteger),
    Column("status", String),
    Column("restrictions", JSONB),
    Column("last_verified_at", DateTime(timezone=True)),
    Column("display_priority", SmallInteger),
    Column("street_name", String),
    Column("from_street", String),
    Column("to_street", String),
)

municipal_feed_records = Table(
    "municipal_feed_records",
    metadata,
    Column("id", UUID),
    Column("source_type", String),
    Column("external_id", String),
    Column("payload", JSONB),
    Column("parking_location_id", UUID),
    Column("synced_at", DateTime(timezone=True)),
)

community_reports = Table(
    "community_reports",
    metadata,
    Column("id", UUID),
    Column("parking_location_id", UUID),
    Column("user_id", UUID),
    Column("photo_url", String),
    Column("ai_extracted_fields", JSONB),
    Column("confirmed_fields", JSONB),
    Column("confidence_score", Numeric),
    Column("created_at", DateTime(timezone=True)),
)

conflicts = Table(
    "conflicts",
    metadata,
    Column("id", UUID),
    Column("parking_location_id", UUID),
    Column("tier1_snapshot", JSONB),
    Column("tier2_snapshot", JSONB),
    Column("status", String),
    Column("resolution", String),
    Column("resolution_source", String),
    Column("resolved_by", UUID),
    Column("opened_at", DateTime(timezone=True)),
    Column("resolved_at", DateTime(timezone=True)),
    Column("decay_deadline", DateTime(timezone=True)),
)

conflict_votes = Table(
    "conflict_votes",
    metadata,
    Column("conflict_id", UUID),
    Column("user_id", UUID),
    Column("supports", String),
    Column("created_at", DateTime(timezone=True)),
)

engine_settings = Table(
    "engine_settings",
    metadata,
    Column("id", Boolean),
    Column("point_match_radius_m", Float),
    Column("segment_snap_radius_m", Float),
    Column("conflict_decay_window", Interval),
    Column("quorum_min_votes", Integer),
    Column("quorum_margin", Numeric),
    Column("updated_at", DateTime(timezone=True)),
)
