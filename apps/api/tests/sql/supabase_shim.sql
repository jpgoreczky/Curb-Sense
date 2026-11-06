-- Minimal Supabase surface so supabase/migrations/*.sql apply to a plain
-- postgis/postgis container (CI and `make test-db`). Never run against Supabase.

-- The postgis image pre-installs PostGIS into `public`; Supabase keeps it in
-- `extensions`, and our migrations call extensions.<fn> explicitly.
drop extension if exists postgis_tiger_geocoder cascade;
drop extension if exists postgis_topology cascade;
drop extension if exists postgis cascade;

create schema if not exists extensions;
create schema if not exists auth;

create table if not exists auth.users (
  id uuid primary key
);

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
end
$$;

create or replace function auth.uid()
returns uuid
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

-- Match Supabase's default search_path so unqualified PostGIS calls resolve.
do $$
begin
  execute format('alter database %I set search_path = "$user", public, extensions', current_database());
end
$$;
