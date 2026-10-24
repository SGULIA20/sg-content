-- Applied to the ScoreMyBiz Supabase project on 21 Oct 2026 as migration "command_center_telegram_and_scoremybiz".
-- Telegram buttons (webhook to sg-command) and ScoreMyBiz in the control room.

alter table command.commands drop constraint commands_target_check;
alter table command.commands add constraint commands_target_check check (target in ('sg-content', 'scoremybiz'));
alter table command.commands drop constraint commands_action_check;
alter table command.commands add constraint commands_action_check
  check (action in ('pause', 'resume', 'stop', 'retry', 'run_produce', 'run_publish', 'smb_ceo_report'));

-- Messages the bot receives that are not control-room commands (clip confirmations for the Mac inbox, notes).
create table command.telegram_inbox (id bigserial primary key, at timestamptz not null default now(), text text not null, consumed_at timestamptz);
alter table command.telegram_inbox enable row level security;
revoke all on command.telegram_inbox from public, anon, authenticated;
revoke all on sequence command.telegram_inbox_id_seq from public, anon, authenticated;

insert into command.control (key, value, updated_by) values ('telegram.webhook', 'false'::jsonb, 'setup');

-- ScoreMyBiz numbers for the control room: totals only, never a customer row. Each block is guarded so a
-- missing table or column gives null for that block instead of failing the whole call.
create or replace function command.smb_numbers() returns jsonb
language plpgsql security definer set search_path = '' stable as $$
declare
  out jsonb := '{}'::jsonb;
  paid constant text[] := array['starter', 'yearly', 'lifetime', 'growth', 'tenyear'];
  today_ist timestamptz := date_trunc('day', now() at time zone 'Asia/Kolkata') at time zone 'Asia/Kolkata';
begin
  begin
    out := out || jsonb_build_object('users', (select jsonb_build_object(
      'total', count(*),
      'paid', count(*) filter (where plan = any(paid)),
      'trial', count(*) filter (where not (coalesce(plan, '') = any(paid)) and registered_at > now() - interval '30 days'),
      'new_today', count(*) filter (where registered_at >= today_ist),
      'new_7d', count(*) filter (where registered_at > now() - interval '7 days'),
      'new_prev_7d', count(*) filter (where registered_at <= now() - interval '7 days' and registered_at > now() - interval '14 days'),
      'active_7d', count(*) filter (where last_active_at > now() - interval '7 days'))
      from public.users where coalesce(founder_access, false) = false and parent_user_id is null));
  exception when others then out := out || jsonb_build_object('users', null);
  end;
  begin
    out := out || jsonb_build_object('money_7d', (select coalesce(jsonb_object_agg(currency, jsonb_build_object('payments', n, 'gross', gross)), '{}'::jsonb)
      from (select coalesce(currency, '?') currency, count(*) n, round(sum(amount), 2) gross from public.payments
            where status in ('success', 'refunded') and paid_at > now() - interval '7 days' group by 1) p));
  exception when others then out := out || jsonb_build_object('money_7d', null);
  end;
  begin
    out := out || jsonb_build_object('support', (select jsonb_build_object(
      'open', count(*) filter (where status = 'open'),
      'oldest_open_at', min(created_at) filter (where status = 'open')) from public.support_tickets));
  exception when others then out := out || jsonb_build_object('support', null);
  end;
  begin
    out := out || jsonb_build_object('jobs', (select coalesce(jsonb_agg(jsonb_build_object('name', name, 'at', started_at, 'status', status,
      'errors', coalesce(jsonb_array_length(case when jsonb_typeof(errors) = 'array' then errors else '[]'::jsonb end), 0)) order by name), '[]'::jsonb)
      from (select distinct on (name) name, started_at, status, errors from public.job_runs order by name, started_at desc) j));
  exception when others then out := out || jsonb_build_object('jobs', null);
  end;
  begin
    out := out || jsonb_build_object('app_errors_24h', (select jsonb_build_object('total', count(*), 'fatal', count(*) filter (where fatal))
      from public.app_errors where created_at > now() - interval '24 hours'));
  exception when others then out := out || jsonb_build_object('app_errors_24h', null);
  end;
  return out || jsonb_build_object('at', now());
end $$;
revoke all on function command.smb_numbers() from public, anon, authenticated;
