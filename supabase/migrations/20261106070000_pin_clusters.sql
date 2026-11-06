-- WP-2b: server-side zoom-adaptive clustering (PRD 3.1).
--
-- Below street zoom the app asks for clusters instead of raw pins. Pins are
-- bucketed by their anchor on a fixed Web Mercator grid whose cell size is
-- cluster_cell_px screen pixels at the requested zoom (512 px Mapbox tiles).
-- The grid is global, so a cell's identity and contents don't change while
-- the user pans, and responses are cache-friendly per (cell, zoom).
--
-- Every cell carries counts and a representative for each filter chip, so
-- "All / Verified only / Free parking only" re-filter on the client with no
-- round-trip (UI-4.2.3):
--   all       every location
--   verified  Tier 1 only (Tier 3 is disputed, Tier 2 is unconfirmed)
--   free      status = 'available'
-- Representative = lowest display_priority (Tier 3, then Tier 1, then
-- Tier 2), then most recently verified, so Tier 1/3 never hide under Tier 2.

alter table engine_settings
  add column cluster_cell_px integer not null default 64
    check (cluster_cell_px between 16 and 512);

-- Web Mercator by formula, not ST_Transform: at city zoom every pin in
-- view is projected, and the closed form is ~10x cheaper per row.
create or replace function mercator_x(lon double precision)
returns double precision
language sql immutable parallel safe
as $$ select 6378137 * radians(lon) $$;

create or replace function mercator_y(lat double precision)
returns double precision
language sql immutable parallel safe
as $$ select 6378137 * ln(tan(pi() / 4 + radians(greatest(least(lat, 85.0511), -85.0511)) / 2)) $$;

create or replace function pin_clusters(
  p_min_lon double precision,
  p_min_lat double precision,
  p_max_lon double precision,
  p_max_lat double precision,
  p_zoom    integer
)
returns table (
  cell_x          bigint,
  cell_y          bigint,
  lon             double precision,
  lat             double precision,
  count_all       integer,
  count_verified  integer,
  count_free      integer,
  rep_all         jsonb,
  rep_verified    jsonb,
  rep_free        jsonb
)
language sql
stable
set search_path = public, extensions
as $$
  with params as (
    -- Metres per cell at this zoom: world width / (tile px * 2^z) * cell px.
    select 40075016.685578488 / (512 * 2 ^ p_zoom) * s.cluster_cell_px as cell_m
    from engine_settings s where s.id
  ),
  cells as (
    -- Grow the viewport outward to whole cells so edge bubbles aren't
    -- partial counts.
    select p.cell_m,
           floor(mercator_x(p_min_lon) / p.cell_m)::bigint as x0,
           floor(mercator_y(p_min_lat) / p.cell_m)::bigint as y0,
           ceil(mercator_x(p_max_lon) / p.cell_m)::bigint - 1 as x1,
           ceil(mercator_y(p_max_lat) / p.cell_m)::bigint - 1 as y1
    from params p
  ),
  prefilter as (
    -- The snapped cell range back in lon/lat, for the GiST index.
    select c.*,
           st_makeenvelope(
             degrees(c.x0 * c.cell_m / 6378137),
             degrees(2 * atan(exp(c.y0 * c.cell_m / 6378137)) - pi() / 2),
             degrees((c.x1 + 1) * c.cell_m / 6378137),
             degrees(2 * atan(exp((c.y1 + 1) * c.cell_m / 6378137)) - pi() / 2),
             4326)::geography as env
    from cells c
  ),
  members as materialized (
    select pf.id, pf.tier, pf.status, pf.display_priority, pf.last_verified_at,
           pf.anchor_lon, pf.anchor_lat,
           floor(mercator_x(pf.anchor_lon) / f.cell_m)::bigint as cx,
           floor(mercator_y(pf.anchor_lat) / f.cell_m)::bigint as cy,
           f.x0, f.x1, f.y0, f.y1
    from prefilter f
    join pin_features pf on pf.geom && f.env
  ),
  in_view as materialized (
    -- Bucket by anchor only: a segment belongs to the cell of its midpoint.
    select * from members where cx between x0 and x1 and cy between y0 and y1
  ),
  agg as (
    select cx, cy,
           avg(anchor_lon) as lon, avg(anchor_lat) as lat,
           count(*)::int as n_all,
           (count(*) filter (where tier = 1))::int as n_verified,
           (count(*) filter (where status = 'available'))::int as n_free
    from in_view group by cx, cy
  ),
  -- Representatives: Tier 3, then Tier 1, then Tier 2; newest first; id breaks ties.
  rep_all as (
    select distinct on (cx, cy) cx, cy, id from in_view
    order by cx, cy, display_priority, last_verified_at desc nulls last, id
  ),
  rep_verified as (
    select distinct on (cx, cy) cx, cy, id from in_view where tier = 1
    order by cx, cy, last_verified_at desc nulls last, id
  ),
  rep_free as (
    select distinct on (cx, cy) cx, cy, id from in_view where status = 'available'
    order by cx, cy, display_priority, last_verified_at desc nulls last, id
  ),
  reps as (
    -- Build JSON only for the chosen pins, not every member.
    select pf.id,
           jsonb_build_object(
             'id', pf.id, 'kind', pf.kind, 'tier', pf.tier, 'status', pf.status,
             'anchor_lon', pf.anchor_lon, 'anchor_lat', pf.anchor_lat,
             'last_verified_at', pf.last_verified_at
           ) as rep
    from pin_features pf
    where pf.id in (select id from rep_all union select id from rep_verified union select id from rep_free)
  )
  select a.cx, a.cy, a.lon, a.lat, a.n_all, a.n_verified, a.n_free,
         ja.rep, jv.rep, jf.rep
  from agg a
  join rep_all ra using (cx, cy)
  join reps ja on ja.id = ra.id
  left join rep_verified rv using (cx, cy)
  left join reps jv on jv.id = rv.id
  left join rep_free rf using (cx, cy)
  left join reps jf on jf.id = rf.id
  order by a.cx, a.cy;
$$;
