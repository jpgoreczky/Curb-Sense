from geoalchemy2 import Geography
from sqlalchemy import Column, MetaData, Table, DateTime, SmallInteger, String
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