-- WP-2a follow-up: a resolved conflict must survive the next feed sync.
--
-- feed_claim is the last {status, restrictions} a municipal feed asserted
-- for this location. When the location's current status/restrictions differ
-- from it, a resolved conflict (community quorum or ops override) decided
-- against the feed. ingest_tier1 then:
--   - feed repeats feed_claim         -> keep the resolved answer
--   - feed now agrees with current    -> normal update
--   - feed changed to something else  -> open a new conflict (no silent overwrite)

alter table parking_locations
  add column feed_claim jsonb,
  add constraint chk_feed_claim_shape
    check (feed_claim is null
           or (feed_claim ? 'status' and feed_claim ? 'restrictions'));

comment on column parking_locations.feed_claim is
  'Last {status, restrictions} asserted by a municipal feed. Differs from the '
  'row''s own status/restrictions only after a conflict resolved against the feed.';

-- Backfill feed-linked rows. For an open conflict the feed's claim is the
-- conflict's Tier 1 snapshot (the row may currently hold the Tier 2 value);
-- otherwise the row is still showing what the feed said.
update parking_locations pl
set feed_claim = coalesce(
  (select jsonb_build_object(
            'status', c.tier1_snapshot -> 'status',
            'restrictions', coalesce(c.tier1_snapshot -> 'restrictions', '{}'::jsonb))
   from conflicts c
   where c.parking_location_id = pl.id
     and c.status = 'open'
     and c.tier1_snapshot ? 'status'),
  jsonb_build_object('status', pl.status, 'restrictions', pl.restrictions))
where pl.municipal_feed_record_id is not null;
