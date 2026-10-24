-- The exact clock (23 Oct 2026). GitHub's own scheduler started none of the morning jobs on 22 and 23 Oct, and the Mac that presses
-- "Run" is often off. Every minute pg_cron looks for a job that is due by Lagos time; if one is, it wakes the sg-command function,
-- which starts the GitHub workflow at once. Needs the GITHUB_TOKEN secret on the function (Actions: read and write on sg-content
-- and arthvan-media); until it is there nothing is started and the GitHub schedules stay the only clock. The engines never post or
-- make a piece twice, so a job started here and again by GitHub's late cron does its work once.
create extension if not exists pg_cron;

create table if not exists command.clock (
  id          serial primary key,
  repo        text not null check (repo in ('sg-content', 'arthvan-media')),
  workflow    text not null,
  inputs      jsonb not null default '{}'::jsonb,
  at_lagos    time,                          -- a daily job: this minute, Lagos time
  every_min   int check (every_min between 5 and 1440),   -- or a repeating job
  catch_up    interval not null default interval '3 hours',  -- a daily job missed (function down) still starts within this window
  enabled     boolean not null default true,
  last_fired  timestamptz,
  note        text,
  check ((at_lagos is null) <> (every_min is null))
);
alter table command.clock enable row level security;
revoke all on command.clock from public, anon, authenticated;

insert into command.clock (repo, workflow, inputs, at_lagos, every_min, note) values
  ('arthvan-media', 'linkedin-personal.yml', '{"mode":"post"}', '04:40', null, 'founder''s daily LinkedIn picture post'),
  ('sg-content',    'produce.yml',           '{}',               '08:15', null, 'make videos (morning)'),
  ('sg-content',    'publish.yml',           '{"channel":"sglearning"}', '09:35', null, 'Learning with SG: Reel, Story, Threads (14:00 India)'),
  ('sg-content',    'produce.yml',           '{}',               '14:45', null, 'make videos (afternoon)'),
  ('arthvan-media', 'daily-post.yml',        '{"mode":"post"}', '15:40', null, 'ScoreMyBiz / Waypoint app posts'),
  ('sg-content',    'publish.yml',           '{"channel":"arthvan"}', '17:05', null, 'SG-MYTH-WORLD: Reel, Story, Threads (21:30 India)'),
  ('sg-content',    'evening.yml',           '{}',               '21:05', null, 'the 9 pm card'),
  ('arthvan-media', 'status.yml',            '{}',               '21:30', null, 'app poster status and scorecard relay'),
  ('arthvan-media', 'telegram-commands.yml', '{}',               null,    15,   'app bot commands');

-- Jobs due now: a daily job whose minute has passed today (Lagos) within its catch-up window and that has not fired today,
-- or a repeating job whose interval has passed.
create or replace function command.clock_due() returns setof command.clock
language sql stable security definer set search_path = '' as $$
  select c.* from command.clock c
  where c.enabled and (
    (c.at_lagos is not null                                     -- timestamps, not times: a 21:30 window must not wrap at midnight
      and (now() at time zone 'Africa/Lagos') >= (now() at time zone 'Africa/Lagos')::date + c.at_lagos
      and (now() at time zone 'Africa/Lagos') <  (now() at time zone 'Africa/Lagos')::date + c.at_lagos + c.catch_up
      and (c.last_fired is null or (c.last_fired at time zone 'Africa/Lagos')::date < (now() at time zone 'Africa/Lagos')::date))
    or (c.every_min is not null and (c.last_fired is null or c.last_fired <= now() - make_interval(mins => c.every_min) + interval '20 seconds')));
$$;
revoke all on function command.clock_due() from public, anon, authenticated;

-- Called every minute by pg_cron: wakes the function only when something is due.
create or replace function command.clock_tick() returns text
language plpgsql security definer set search_path = '' as $$
declare wait timestamptz;
begin
  if not exists (select 1 from command.clock_due()) then
    return 'idle';
  end if;
  select (value #>> '{}')::timestamptz into wait from command.control where key = 'clock.wait_until';
  if wait > now() then
    return 'waiting';                       -- no GITHUB_TOKEN yet: the function asked not to be woken for 10 minutes
  end if;
  perform net.http_post(
    url := 'https://xiidltxcsetevaverqkx.supabase.co/functions/v1/sg-command/clock',
    headers := jsonb_build_object('content-type', 'application/json',
      'x-hook-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'sg_command_hook')),
    body := '{}'::jsonb, timeout_milliseconds := 30000);
  return 'woke';
end $$;
revoke all on function command.clock_tick() from public, anon, authenticated;

insert into command.control (key, value, updated_by) values ('clock.wait_until', '"1970-01-01T00:00:00Z"'::jsonb, 'setup')
  on conflict (key) do nothing;

select cron.schedule('sg-command-clock', '* * * * *', 'select command.clock_tick()');
