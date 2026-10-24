-- Applied to the ScoreMyBiz Supabase project on 22 Oct 2026 as migration "command_center_live_refresh".
-- Live status: the page asks for a refresh (at most every 20 s); the sg-command function reads the latest state of the
-- public sg-content and arthvan-media repos from GitHub and stores it in command.status.
insert into command.control (key, value, updated_by) values ('github.last_refresh', '"1970-01-01T00:00:00Z"'::jsonb, 'setup')
  on conflict (key) do nothing;
insert into command.control (key, value, updated_by) values ('github.cache', '{}'::jsonb, 'setup')
  on conflict (key) do nothing;

create or replace function command.refresh() returns text
language plpgsql security definer set search_path = '' as $$
declare last timestamptz;
begin
  select (value #>> '{}')::timestamptz into last from command.control where key = 'github.last_refresh' for update;
  if last > now() - interval '20 seconds' then
    return 'fresh';
  end if;
  update command.control set value = to_jsonb(now()), updated_at = now(), updated_by = 'page' where key = 'github.last_refresh';
  perform net.http_post(
    url := 'https://xiidltxcsetevaverqkx.supabase.co/functions/v1/sg-command/refresh',
    headers := jsonb_build_object('content-type', 'application/json',
      'x-hook-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'sg_command_hook')),
    body := '{}'::jsonb, timeout_milliseconds := 30000);
  return 'requested';
end $$;
revoke all on function command.refresh() from public, anon, authenticated;
