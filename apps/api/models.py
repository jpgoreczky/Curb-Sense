from geoalchemy2 import Geography
from sqlalchemy import Column, MetaData, Table, DateTime, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

parking_locations = Table(
    "parking_locations",
    metadata,
    Column("id", UUID),
    Column("geom", Geography(srid=4326)),
    Column("tier", SmallInteger),
    Column("status", String),
    Column("restrictions", JSONB),
    Column("last_verified_at", DateTime(timezone=True)),
    Column("municipal_feed_record_id", UUID),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
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
    Column("resolved_by", UUID),
    Column("opened_at", DateTime(timezone=True)),
    Column("resolved_at", DateTime(timezone=True)),
    Column("decay_deadline", DateTime(timezone=True)),
)