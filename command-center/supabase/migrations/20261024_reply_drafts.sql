-- YouTube reply drafts (24 Oct 2026): engine/ytreplies.py sends drafts here; each goes to the founder's Telegram with Post / Skip
-- buttons; approved drafts are handed back to the next run, which posts them on YouTube.
create table if not exists command.reply_drafts (
  id          bigserial primary key,
  platform    text not null default 'youtube',
  channel     text not null,
  comment_id  text not null unique,
  video_id    text,
  author      text,
  comment     text,
  draft       text not null,
  state       text not null default 'pending' check (state in ('pending', 'approved', 'skipped', 'posted', 'failed')),
  created_at  timestamptz not null default now(),
  decided_at  timestamptz,
  posted_at   timestamptz
);
alter table command.reply_drafts enable row level security;
revoke all on command.reply_drafts from public, anon, authenticated;
