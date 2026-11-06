-- WP-2a: curb segments, community conflict voting, engine settings,
-- viewport view, and contributor privacy.
--
-- Geometry model after this migration (parking_locations.geom):
--   POINT       a single sign / spot (community reports with no segment nearby)
--   LINESTRING  a curb segment. The line is the street CENTERLINE stretch;
--               curb_side says which side of it ('left' | 'right', relative to
--               the line's digitized direction). The app draws it with
--               Mapbox `line-offset` (positive = right of direction).
--   POLYGON     an off-street lot.
-- Event overlays (snow emergencies, parades) are NOT stored here; they get
-- their own table with BACK-2.7.

-- ---------------------------------------------------------------------
-- 1. engine_settings: one row of tunables read by the ingestion engine.
-- ---------------------------------------------------------------------
create table engine_settings (
  id                     boolean primary key default true check (id),
  point_match_radius_m   double precision not null default 15,
  segment_snap_radius_m  double precision not null default 20,
  conflict_decay_window  interval not null default interval '48 hours',
  quorum_min_votes       integer not null default 3 check (quorum_min_votes >= 1),
  quorum_margin          numeric not null default 0.75
                           check (quorum_margin > 0.5 and quorum_margin <= 1),
  updated_at             timestamptz not null default now()
);

insert into engine_settings default values;

alter table engine_settings enable row level security;
-- No policies: only the API (service role / owner) reads it.

-- ---------------------------------------------------------------------
-- 2. parking_locations: allow curb segments.
-- ---------------------------------------------------------------------
alter table parking_locations drop constraint chk_geom_type;

alter table parking_locations
  add column curb_side   text,
  add column street_name text,
  add column from_street text,
  add column to_street   text,
  add column osm_way_id  bigint,
  -- Lower sorts first. Tier 3 and Tier 1 always outrank Tier 2, so viewport
  -- LIMITs and cluster representatives never bury high-priority data.
  add column display_priority smallint
    generated always as (case tier when 3 then 0 when 1 then 1 else 2 end) stored;

alter table parking_locations
  add constraint chk_geom_type
    check (extensions.geometrytype(geom::extensions.geometry)
           in ('POINT', 'LINESTRING', 'POLYGON')),
  add constraint chk_curb_side_value
    check (curb_side in ('left', 'right')),
  -- Segments must say which curb they describe; points and lots must not.
  add constraint chk_curb_side_iff_segment
    check ((extensions.geometrytype(geom::extensions.geometry) = 'LINESTRING')
           = (curb_side is not null));

create index idx_parking_locations_priority
  on parking_locations (display_priority, last_verified_at desc);

create index idx_parking_locations_osm_way
  on parking_locations (osm_way_id, curb_side)
  where osm_way_id is not null;

-- ---------------------------------------------------------------------
-- 3. conflicts: resolution source, one open conflict per location.
-- ---------------------------------------------------------------------
alter table conflicts
  add column resolution_source text,
  add constraint chk_resolution_source
    check (resolution_source in ('community_quorum', 'ops_override'));

create unique index uq_conflicts_one_open_per_location
  on conflicts (parking_location_id)
  where status = 'open';

-- ---------------------------------------------------------------------
-- 4. conflict_votes: one vote per user per conflict (changeable).
--    supports = which side of the disagreement the voter confirmed.
-- ---------------------------------------------------------------------
create table conflict_votes (
  conflict_id uuid not null references conflicts(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  supports    text not null check (supports in ('tier1', 'tier2', 'unsure')),
  created_at  timestamptz not null default now(),
  primary key (conflict_id, user_id)
);

alter table conflict_votes enable row level security;

create policy "Users read own conflict votes"
  on conflict_votes for select
  to authenticated
  using (user_id = auth.uid());

-- ---------------------------------------------------------------------
-- 5. Privacy: community reports are no longer publicly readable.
--    user_id + photo + location + time = a contributor's movement history.
--    Public pin detail goes through the API, which never returns user_id.
-- ---------------------------------------------------------------------
drop policy "Public read access to community reports" on community_reports;

create policy "Users read own community reports"
  on community_reports for select
  to authenticated
  using (user_id = auth.uid());

-- ---------------------------------------------------------------------
-- 6. Spatial helpers.
-- ---------------------------------------------------------------------

-- Which side of a line a point is on, relative to the line's direction.
-- Samples the local direction around the closest point, so it works on
-- curved segments. Sign of the 2D cross product is unaffected by lon/lat
-- scaling, so planar math on 4326 is safe here.
create or replace function curb_side_of(line extensions.geometry, pt extensions.geometry)
returns text
language sql
immutable
strict
set search_path = public, extensions
as $$
  with f as (
    select st_linelocatepoint(line, pt) as t
  ),
  ab as (
    select st_lineinterpolatepoint(line, greatest(t - 0.001, 0)) as a,
           st_lineinterpolatepoint(line, least(t + 0.001, 1))    as b
    from f
  )
  select case
           when (st_x(b) - st_x(a)) * (st_y(pt) - st_y(a))
              - (st_y(b) - st_y(a)) * (st_x(pt) - st_x(a)) > 0
           then 'left'
           else 'right'
         end
  from ab;
$$;

-- Target location for a community report at p_point.
-- Preference order: a curb segment on the SAME side of the street within
-- segment_snap_radius_m, then the nearest point/lot within
-- point_match_radius_m. NULL means "create a new point location".
create or replace function match_location_for_report(p_point extensions.geography)
returns uuid
language sql
stable
set search_path = public, extensions
as $$
  with s as (
    select point_match_radius_m, segment_snap_radius_m
    from engine_settings where id
  ),
  candidates as (
    select pl.id, st_distance(pl.geom, p_point) as d, 0 as pref
    from parking_locations pl, s
    where geometrytype(pl.geom::geometry) = 'LINESTRING'
      and st_dwithin(pl.geom, p_point, s.segment_snap_radius_m)
      and pl.curb_side = curb_side_of(pl.geom::geometry, p_point::geometry)
    union all
    select pl.id, st_distance(pl.geom, p_point) as d, 1 as pref
    from parking_locations pl, s
    where geometrytype(pl.geom::geometry) in ('POINT', 'POLYGON')
      and st_dwithin(pl.geom, p_point, s.point_match_radius_m)
  )
  select id from candidates
  order by pref, d
  limit 1;
$$;

-- Existing location for a municipal feed geometry (used only when the feed
-- record isn't already linked to a location).
--   LINESTRING: same curb, endpoints within point_match_radius_m. A segment
--               digitized in the opposite direction matches with the
--               opposite curb_side label (same physical curb).
--   POINT:      nearest point within point_match_radius_m.
--   POLYGON:    any intersecting lot.
create or replace function match_location_for_feed(p_geom extensions.geography, p_curb_side text)
returns uuid
language sql
stable
set search_path = public, extensions
as $$
  with s as (
    select point_match_radius_m as r from engine_settings where id
  ),
  q as (
    select geometrytype(p_geom::geometry) as gtype,
           st_startpoint(p_geom::geometry)::geography as qs,
           st_endpoint(p_geom::geometry)::geography as qe
  )
  select pl.id
  from parking_locations pl, s, q
  where st_dwithin(pl.geom, p_geom, s.r)            -- index-assisted prefilter
    and geometrytype(pl.geom::geometry) = q.gtype
    and (
      q.gtype = 'POINT'
      or (q.gtype = 'POLYGON' and st_intersects(pl.geom, p_geom))
      or (q.gtype = 'LINESTRING' and (
            (pl.curb_side = p_curb_side
             and st_dwithin(st_startpoint(pl.geom::geometry)::geography, q.qs, s.r)
             and st_dwithin(st_endpoint(pl.geom::geometry)::geography,   q.qe, s.r))
         or (pl.curb_side <> p_curb_side
             and st_dwithin(st_startpoint(pl.geom::geometry)::geography, q.qe, s.r)
             and st_dwithin(st_endpoint(pl.geom::geometry)::geography,   q.qs, s.r))
      ))
    )
  order by st_distance(pl.geom, p_geom)
  limit 1;
$$;

-- Serialize concurrent writers that could create a location in the same
-- area. Takes a transaction-scoped advisory lock on every geohash-6 cell
-- (~1.2 x 0.6 km) touched by the point's buffer. Any two points within
-- p_radius_m of each other share at least one cell, so they can't both
-- miss each other and insert duplicates. Cells are locked in sorted order
-- to avoid deadlocks.
create or replace function lock_area(p_point extensions.geography, p_radius_m double precision)
returns void
language plpgsql
set search_path = public, extensions
as $$
declare
  cell text;
begin
  for cell in
    select distinct st_geohash(d.geom, 6)
    from st_dumppoints(st_envelope(st_buffer(p_point, p_radius_m)::geometry)) as d
    order by 1
  loop
    perform pg_advisory_xact_lock(hashtextextended('curb_area:' || cell, 0));
  end loop;
end;
$$;

-- ---------------------------------------------------------------------
-- 7. pin_features: what the map renders. Every geometry type gets an
--    anchor point (point itself, segment midpoint, lot point-on-surface),
--    so callers never call ST_X on a non-point.
--    security_invoker keeps RLS in force for direct client reads.
-- ---------------------------------------------------------------------
create view pin_features
with (security_invoker = true)
as
select
  pl.id,
  case extensions.geometrytype(pl.geom::extensions.geometry)
    when 'POINT' then 'point'
    when 'LINESTRING' then 'segment'
    else 'lot'
  end as kind,
  extensions.st_x(a.anchor) as anchor_lon,
  extensions.st_y(a.anchor) as anchor_lat,
  extensions.st_asgeojson(pl.geom::extensions.geometry, 6)::jsonb as geometry,
  pl.geom,
  pl.curb_side,
  pl.tier,
  pl.status,
  pl.restrictions,
  pl.last_verified_at,
  pl.display_priority,
  pl.street_name,
  pl.from_street,
  pl.to_street
from parking_locations pl
cross join lateral (
  select case extensions.geometrytype(pl.geom::extensions.geometry)
           when 'POINT' then pl.geom::extensions.geometry
           when 'LINESTRING' then extensions.st_lineinterpolatepoint(pl.geom::extensions.geometry, 0.5)
           else extensions.st_pointonsurface(pl.geom::extensions.geometry)
         end as anchor
) a;
