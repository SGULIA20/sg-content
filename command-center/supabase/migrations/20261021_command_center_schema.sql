-- Applied to the ScoreMyBiz Supabase project (xiidltxcsetevaverqkx) on 21 Oct 2026 as migration "command_center_schema".
-- Founder control room for sg-content (and later ScoreMyBiz / Waypoint). Walled off: no API exposure, no anon/authenticated access.
create extension if not exists pg_net with schema extensions;

create schema if not exists command;
revoke all on schema command from public, anon, authenticated;

create table command.control (key text primary key, value jsonb not null, updated_at timestamptz not null default now(), updated_by text);
insert into command.control (key, value, updated_by) values ('sg-content.paused', 'false'::jsonb, 'setup');

create table command.status (source text not null, key text not null, payload jsonb not null, updated_at timestamptz not null default now(),
  primary key (source, key));

create table command.events (id bigserial primary key, at timestamptz not null default now(), source text not null, kind text not null,
  message text not null, payload jsonb not null default '{}'::jsonb);
create index on command.events (at desc);

create table command.commands (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  target text not null default 'sg-content' check (target in ('sg-content')),
  action text not null check (action in ('pause', 'resume', 'stop', 'retry', 'run_produce', 'run_publish')),
  args jsonb not null default '{}'::jsonb,
  requested_via text not null default 'page' check (requested_via in ('page', 'telegram', 'claude')),
  note text,
  state text not null default 'queued' check (state in ('queued', 'sent', 'done', 'failed', 'rejected')),
  result text,
  done_at timestamptz
);
create index on command.commands (created_at desc);

alter table command.control enable row level security;
alter table command.status enable row level security;
alter table command.events enable row level security;
alter table command.commands enable row level security;
revoke all on all tables in schema command from public, anon, authenticated;
revoke all on all sequences in schema command from public, anon, authenticated;

-- Shared secrets live in Vault, never in code or the public repo.
select vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'sg_command_hook', 'trigger -> sg-command edge function');
select vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'sg_command_ingest', 'GitHub Actions -> sg-command edge function (copy into GitHub secret SG_COMMAND_KEY)');

create or replace function command.on_command_insert() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  perform net.http_post(
    url := 'https://xiidltxcsetevaverqkx.supabase.co/functions/v1/sg-command/hook',
    headers := jsonb_build_object('content-type', 'application/json',
      'x-hook-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'sg_command_hook')),
    body := jsonb_build_object('id', new.id),
    timeout_milliseconds := 15000);
  return new;
end $$;
revoke all on function command.on_command_insert() from public, anon, authenticated;

create trigger command_insert after insert on command.commands for each row execute function command.on_command_insert();
