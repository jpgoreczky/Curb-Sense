-- Curb Sense: core PostGIS schema
-- Tables: profiles, parking_locations, municipal_feed_records,
--         community_reports, conflicts

create extension if not exists postgis with schema extensions;

-- ---------------------------------------------------------------------
-- profiles: minimal placeholder extending Supabase's built-in auth.users.
-- BACK-2.5 will extend this with points/badges/resolution history.
-- ---------------------------------------------------------------------
create table profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- parking_locations: the core map entity. Supports both individual pins
-- (Point) and event-radius overlays (Polygon) in one geometry column.
-- tier/status are persisted (not derived) for fast viewport filtering.
-- ---------------------------------------------------------------------
create table parking_locations (
  id                       uuid primary key default gen_random_uuid(),
  geom                     extensions.geography not null,
  tier                     smallint not null,
  status                   text not null,
  restrictions             jsonb not null default '{}'::jsonb,
  last_verified_at         timestamptz,
  municipal_feed_record_id uuid,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),

  constraint chk_geom_type
    check (extensions.geometrytype(geom::extensions.geometry) in ('POINT', 'POLYGON')),
  constraint chk_tier
    check (tier in (1, 2, 3)),
  constraint chk_status
    check (status in ('available', 'conditional', 'restricted'))
);

create index idx_parking_locations_geom on parking_locations using gist (geom);
create index idx_parking_locations_tier_status on parking_locations (tier, status);

-- ---------------------------------------------------------------------
-- municipal_feed_records: Open311 / permit / sweeping feed ingestion.
-- One record generally maps to (and updates) one parking_locations row.
-- ---------------------------------------------------------------------
create table municipal_feed_records (
  id                  uuid primary key default gen_random_uuid(),
  source_type         text not null,
  external_id         text not null,
  payload             jsonb not null,
  parking_location_id uuid references parking_locations(id) on delete set null,
  synced_at           timestamptz not null default now(),

  constraint chk_source_type
    check (source_type in ('open311', 'permit', 'street_sweeping', 'manual_override')),
  constraint uq_source_external unique (source_type, external_id)
);

create index idx_municipal_feed_records_location on municipal_feed_records (parking_location_id);

alter table parking_locations
  add constraint fk_parking_locations_municipal_feed
  foreign key (municipal_feed_record_id)
  references municipal_feed_records(id)
  on delete set null;

-- ---------------------------------------------------------------------
-- community_reports: Tier 2 submissions. AI-parsed fields are stored
-- separately from user-confirmed fields per AI-3.4's confirmation step
-- (AI output is never written as final data without user confirmation).
-- ---------------------------------------------------------------------
create table community_reports (
  id                   uuid primary key default gen_random_uuid(),
  parking_location_id  uuid not null references parking_locations(id) on delete cascade,
  user_id              uuid not null references auth.users(id),
  photo_url            text,
  ai_extracted_fields  jsonb,
  confirmed_fields      jsonb not null default '{}'::jsonb,
  confidence_score     numeric,
  created_at           timestamptz not null default now()
);

create index idx_community_reports_location on community_reports (parking_location_id);
create index idx_community_reports_user on community_reports (user_id);

-- ---------------------------------------------------------------------
-- conflicts: Tier 3 flagging. Snapshots both sides of the disagreement
-- at flag time, so BACK-2.3's adjudication has stable data to compare
-- even as the underlying records continue to change.
-- ---------------------------------------------------------------------
create table conflicts (
  id                    uuid primary key default gen_random_uuid(),
  parking_location_id   uuid not null references parking_locations(id) on delete cascade,
  tier1_snapshot         jsonb not null,
  tier2_snapshot         jsonb not null,
  status                text not null default 'open',
  resolution            text,
  resolved_by           uuid references auth.users(id),
  opened_at             timestamptz not null default now(),
  resolved_at           timestamptz,
  decay_deadline        timestamptz not null,

  constraint chk_conflict_status
    check (status in ('open', 'resolved', 'decayed'))
);

create index idx_conflicts_location on conflicts (parking_location_id);
create index idx_conflicts_status_deadline on conflicts (status, decay_deadline);

-- ---------------------------------------------------------------------
-- Row Level Security: enabled now with a minimal default-deny posture.
-- Real policies (who can write what) are BACK-2.5's responsibility once
-- auth/profile logic exists. Flagging this explicitly rather than
-- leaving RLS off, since these tables will be queried directly from
-- the mobile client, not just through the backend.
-- ---------------------------------------------------------------------
alter table profiles enable row level security;
alter table parking_locations enable row level security;
alter table municipal_feed_records enable row level security;
alter table community_reports enable row level security;
alter table conflicts enable row level security;

-- Public read access to parking data — this is core map functionality,
-- viewable without authentication (matches the PRD's discovery flow).
create policy "Public read access to parking locations"
  on parking_locations for select
  using (true);

create policy "Public read access to community reports"
  on community_reports for select
  using (true);

-- Writes remain fully locked down (no policy = no access under RLS)
-- until BACK-2.5 defines proper authenticated-write policies.