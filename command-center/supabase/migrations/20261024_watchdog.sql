-- The clock watchdog (founder, 24 Oct 2026). On 24 Oct every clock job fired once and then stopped for five hours, and nobody
-- was told. Every 10 minutes pg_cron wakes the sg-watchdog function, which tells the founder on Telegram (once per problem) when
-- a clock job is 30 minutes late or when a GitHub run of a clock workflow fails. Lateness is worked out here; failed runs there.
create table if not exists command.watchdog_seen (key text primary key, at timestamptz not null default now());
alter table command.watchdog_seen enable row level security;
revoke all on command.watchdog_seen from public, anon, authenticated;

insert into command.control (key, value, updated_by) values ('watchdog.since', to_jsonb(now()), 'migration')
on conflict (key) do nothing;

-- A daily job whose minute (today's or yesterday's, so a late-evening slot is still checked after midnight) passed more than
-- 30 minutes ago without a start, or a repeating job 30 minutes past its interval. Slots before the watchdog existed are ignored,
-- and sg-content jobs are not late while sg-content is paused (the clock holds them on purpose).
create or replace function command.clock_late() returns table (id int, repo text, workflow text, note text, due timestamptz, key text)
language sql stable security definer set search_path = '' as $$
  with since as (select coalesce((select (value #>> '{}')::timestamptz from command.control where key = 'watchdog.since'), now()) as t),
  paused as (select coalesce((select value = 'true'::jsonb from command.control where key = 'sg-content.paused'), false) as p)
  select c.id, c.repo, c.workflow, c.note, s.slot, 'late:' || c.id || ':' || s.slot
  from command.clock c
  cross join lateral (select ((now() at time zone 'Africa/Lagos')::date - d + c.at_lagos) at time zone 'Africa/Lagos' as slot
                      from generate_series(0, 1) d) s
  where c.enabled and c.at_lagos is not null
    and s.slot > (select t from since) and s.slot < now() - interval '30 minutes'
    and (c.last_fired is null or c.last_fired < s.slot)
    and not (c.repo = 'sg-content' and (select p from paused))
  union all
  select c.id, c.repo, c.workflow, c.note, coalesce(c.last_fired, (select t from since)) + make_interval(mins => c.every_min),
         'stall:' || c.id || ':' || coalesce(c.last_fired::text, 'never')
  from command.clock c
  where c.enabled and c.every_min is not null
    and coalesce(c.last_fired, (select t from since)) < now() - make_interval(mins => c.every_min) - interval '30 minutes'
    and not (c.repo = 'sg-content' and (select p from paused));
$$;
revoke all on function command.clock_late() from public, anon, authenticated;

create or replace function command.watchdog_tick() returns void
language plpgsql security definer set search_path = '' as $$
begin
  delete from command.watchdog_seen where at < now() - interval '14 days';
  perform net.http_post(
    url := 'https://xiidltxcsetevaverqkx.supabase.co/functions/v1/sg-watchdog',
    headers := jsonb_build_object('content-type', 'application/json',
      'x-hook-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'sg_command_hook')),
    body := '{}'::jsonb, timeout_milliseconds := 30000);
end $$;
revoke all on function command.watchdog_tick() from public, anon, authenticated;

select cron.schedule('sg-watchdog', '3-59/10 * * * *', 'select command.watchdog_tick()');
