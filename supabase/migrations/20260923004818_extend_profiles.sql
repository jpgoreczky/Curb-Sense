-- BACK-2.5: extend profiles with contributor fields (points, badges,
-- resolved-conflicts count). GAM-6.1/6.2 build the actual point-awarding
-- and badge-eligibility logic against this structure later — this
-- migration only adds the columns, matching how BACK-2.3 built generic
-- write paths ahead of the upstream tasks that populate them.

alter table profiles
  add column points integer not null default 0,
  add column badges jsonb not null default '[]'::jsonb,
  add column resolved_conflicts_count integer not null default 0,
  add column updated_at timestamptz not null default now();

-- Account creation: auto-create a profiles row whenever a new Supabase
-- Auth user is created, so every authenticated user has a corresponding
-- profile from the moment they sign up (rather than requiring the app
-- to remember to create one, or leaving auth.users and profiles able to
-- drift out of sync).
create function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id)
  values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();