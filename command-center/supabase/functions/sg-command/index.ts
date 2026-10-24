// sg-command: the founder control room's only door to GitHub, ScoreMyBiz and the Telegram bot.
//   POST /hook             a new row in command.commands (sent by the database trigger, x-hook-secret)
//   POST /ingest           a pipeline reports its status (x-sg-key = Vault sg_command_ingest); answers {paused}
//   GET  /control          a pipeline asks whether it is paused (x-sg-key)
//   POST /pause            Telegram /pause and /resume keep the shared flag in step (x-sg-key)
//   POST /telegram         the bot's webhook (x-telegram-bot-api-secret-token = Vault telegram_webhook_secret)
//   POST /telegram-setup   {token, chat_id, on}: store the bot in Vault and switch the webhook on or off (x-sg-key)
//   POST /telegram-inbox   messages that are not commands, for the Mac inbox (x-sg-key); answers {webhook, messages}
//   POST /refresh          live status from the public sg-content and arthvan-media repos (x-hook-secret; command.refresh())
//   POST /clock            start the GitHub jobs that are due by Lagos time (x-hook-secret; pg_cron via command.clock_tick())
// Only the actions below exist; anything else is rejected and recorded.
import postgres from "npm:postgres@3.4.5";

const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, { prepare: false, max: 1 });
const SELF = "https://xiidltxcsetevaverqkx.supabase.co/functions/v1/sg-command";
const GH = "https://api.github.com/repos/SGULIA20/sg-content";
const SMB_CEO_REPORT = "https://scoremybiz.com/.netlify/functions/ceo-report";
const CHANNELS = ["sglearning", "arthvan"];
const CHANNEL_NAME: Record<string, string> = { sglearning: "Learning with SG", arthvan: "SG-MYTH-WORLD" };
const KINDS = ["short", "long"];
const PIECE = /^\d{4}-\d{2}-\d{2}-(sglearning|arthvan)-(short|long)$/;
const WORKFLOWS = ["produce.yml", "publish.yml"];
const DONE = ["uploaded", "posted"];

class Rejected extends Error {}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function same(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function vault(name: string): Promise<string> {
  const r = await sql`select decrypted_secret from vault.decrypted_secrets where name = ${name}`;
  return r[0]?.decrypted_secret ?? "";
}

async function vaultSet(name: string, value: string) {
  const r = await sql`select id from vault.secrets where name = ${name}`;
  if (r.length) await sql`select vault.update_secret(${r[0].id}, ${value})`;
  else await sql`select vault.create_secret(${value}, ${name})`;
}

async function gh(method: string, path: string, body?: unknown, base = GH) {
  const token = Deno.env.get("GITHUB_TOKEN");
  if (!token) throw new Error("GITHUB_TOKEN is not set on the sg-command function");
  const res = await fetch(base + path, {
    method,
    headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json", "x-github-api-version": "2022-11-28" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`GitHub ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.status === 204 ? null : res.json();
}

const dispatch = (workflow: string, inputs: Record<string, string>) =>
  gh("POST", `/actions/workflows/${workflow}/dispatches`, { ref: "main", inputs });

async function setPaused(flag: boolean, by: string) {
  await sql`update command.control set value = ${sql.json(flag)}, updated_at = now(), updated_by = ${by} where key = 'sg-content.paused'`;
}

async function isPaused(): Promise<boolean> {
  const r = await sql`select value from command.control where key = 'sg-content.paused'`;
  return r[0]?.value === true;
}

async function event(kind: string, message: string, payload: postgres.JSONValue = {}) {
  await sql`insert into command.events (source, kind, message, payload) values ('sg-command', ${kind}, ${message}, ${sql.json(payload)})`;
}

function onlyArg(v: unknown): string {
  if (v === undefined || v === null || v === "") return "";
  const parts = String(v).split(",").map((s) => s.trim());
  for (const p of parts) {
    const [c, k] = p.split(":");
    if (!CHANNELS.includes(c) || !KINDS.includes(k)) throw new Rejected(`unknown channel:kind "${p}"`);
  }
  return parts.join(",");
}

async function execute(action: string, a: Record<string, unknown>, via: string): Promise<string> {
  switch (action) {
    case "pause":
    case "resume":
      await setPaused(action === "pause", via);
      return action === "pause" ? "Paused: no new runs will make or post anything until resume." : "Resumed: the next run carries on.";
    case "stop": {
      let n = 0;
      for (const wf of WORKFLOWS) {
        for (const status of ["in_progress", "queued"]) {
          const r = await gh("GET", `/actions/workflows/${wf}/runs?status=${status}&per_page=20`);
          for (const run of r.workflow_runs ?? []) {
            await gh("POST", `/actions/runs/${run.id}/cancel`);
            n++;
          }
        }
      }
      return n ? `Cancelled ${n} running job(s). Pause too if you want later runs to stay off.` : "Nothing was running.";
    }
    case "retry": {
      const m = PIECE.exec(String(a.piece_id ?? ""));
      if (!m) throw new Rejected("retry needs a piece id like 2026-10-21-sglearning-short");
      await dispatch("produce.yml", { only: `${m[1]}:${m[2]}`, max: "1" });
      return `Started produce for ${m[1]}:${m[2]}; it resumes ${a.piece_id} from its last good step.`;
    }
    case "run_produce": {
      const max = Number(a.max ?? 3);
      if (!Number.isInteger(max) || max < 1 || max > 3) throw new Rejected("max must be 1 to 3");
      const inputs: Record<string, string> = { max: String(max), dry_run: a.dry_run === true ? "true" : "false" };
      const only = onlyArg(a.only);
      if (only) inputs.only = only;
      await dispatch("produce.yml", inputs);
      return `Started produce (${only || "everything the buffer needs"}, max ${max}${a.dry_run === true ? ", dry run" : ""}).`;
    }
    case "run_publish": {
      if (!CHANNELS.includes(String(a.channel))) throw new Rejected("channel must be sglearning or arthvan");
      await dispatch("publish.yml", { channel: String(a.channel) });
      return `Started publish for ${a.channel} (Reel + Story + Threads that are due).`;
    }
    case "app_post":                                   // ScoreMyBiz / Waypoint posts of the day (never twice: the engine checks)
      await gh("POST", "/actions/workflows/daily-post.yml/dispatches", { ref: "main", inputs: { mode: "post" } }, CLOCK_REPOS["arthvan-media"]);
      return "Started today's app posts (ScoreMyBiz / Waypoint). Anything already posted today is skipped.";
    case "app_linkedin":
      await gh("POST", "/actions/workflows/linkedin-personal.yml/dispatches", { ref: "main", inputs: { mode: "post" } }, CLOCK_REPOS["arthvan-media"]);
      return "Started today's LinkedIn post. If it is already out, nothing is posted twice.";
    case "smb_ceo_report": {
      const res = await fetch(SMB_CEO_REPORT, {
        method: "POST",
        headers: { "content-type": "application/json", "x-command-key": await vault("sg_command_ingest") },
        body: JSON.stringify({ send: true, format: "json" }),
      });
      if (!res.ok) throw new Error(`ScoreMyBiz ${res.status}: ${(await res.text()).slice(0, 160)}`);
      const out = await res.json();
      return out.emailed ? "ScoreMyBiz CEO report built and emailed." : "ScoreMyBiz CEO report built, but not emailed (CEO_REPORT_EMAIL or email sending is not set up).";
    }
    default:
      throw new Rejected(`unknown action "${action}"`);
  }
}

async function run(id: number): Promise<{ state: string; result: string }> {
  const rows = await sql`update command.commands set state = 'sent' where id = ${id} and state = 'queued' returning *`;
  if (!rows.length) return { state: "skipped", result: "" };
  const cmd = rows[0];
  let state = "done", result = "";
  try {
    result = await execute(cmd.action, cmd.args ?? {}, cmd.requested_via);
  } catch (e) {
    state = e instanceof Rejected ? "rejected" : "failed";
    result = String((e as Error).message).slice(0, 300);
  }
  await sql`update command.commands set state = ${state}, result = ${result}, done_at = now() where id = ${id}`;
  await event(`command.${state}`, `${cmd.action}: ${result}`, { id, action: cmd.action, args: cmd.args });
  return { state, result };
}

async function hook(req: Request): Promise<Response> {
  if (!same(req.headers.get("x-hook-secret") ?? "", await vault("sg_command_hook"))) return json({ error: "forbidden" }, 403);
  const { id } = await req.json();
  const out = await run(Number(id));
  return json({ ok: out.state === "done" || out.state === "skipped", ...out });
}

// ---------- live status from GitHub ----------
const API = "https://api.github.com";
const DAY_MS = 86400e3;
type Cache = Record<string, { etag: string | null; body: unknown }>;

// Conditional requests: an unchanged answer is a 304, which GitHub does not count against the hourly limit.
async function ghGet(url: string, cache: Cache, opts: { sha?: boolean; slim?: (b: any) => unknown } = {}) {
  const headers: Record<string, string> = { accept: opts.sha ? "application/vnd.github.sha" : "application/vnd.github+json",
    "user-agent": "sg-command", "x-github-api-version": "2022-11-28" };
  const token = Deno.env.get("GITHUB_TOKEN");
  if (token) headers.authorization = `Bearer ${token}`;
  const hit = cache[url];
  if (hit?.etag) headers["if-none-match"] = hit.etag;
  const res = await fetch(url, { headers });
  if (res.status === 304 && hit) return { changed: false, body: hit.body as any };
  if (!res.ok) throw new Error(`GitHub ${res.status}${res.headers.get("x-ratelimit-remaining") === "0" ? ": hourly limit reached" : ""}`);
  const raw = opts.sha ? (await res.text()).trim() : await res.json();
  const body = opts.slim ? opts.slim(raw) : raw;
  cache[url] = { etag: res.headers.get("etag"), body };
  return { changed: true, body: body as any };
}

async function rawFile(repo: string, sha: string, path: string, json = true): Promise<any> {
  const res = await fetch(`https://raw.githubusercontent.com/SGULIA20/${repo}/${sha}/${path}`);
  if (!res.ok) return null;
  return json ? res.json().catch(() => null) : res.text();
}

const slimRuns = (b: any) => (b.workflow_runs ?? []).map((w: any) => ({ id: w.id, name: w.name, status: w.status, conclusion: w.conclusion,
  event: w.event, created_at: w.created_at, started_at: w.run_started_at, updated_at: w.updated_at, url: w.html_url }));
const lastKeys = (d: any, n = 3) => (d && typeof d === "object") ? Object.fromEntries(Object.keys(d).sort().slice(-n).map((k) => [k, d[k]])) : {};

async function sgSnapshot(sha: string) {
  const list = await ghGet(`${API}/repos/SGULIA20/sg-content/contents/pieces?ref=${sha}`, {},       // once per new commit: not worth caching
    { slim: (b: any) => (Array.isArray(b) ? b : []).map((f: any) => f.name) });
  const today = new Date(Date.now() + 5.5 * 3600e3);                       // IST, the pipeline's calendar
  const from = new Date(today.getTime() - 3 * DAY_MS).toISOString().slice(0, 10), to = new Date(today.getTime() + 14 * DAY_MS).toISOString().slice(0, 10);
  const names = (list.body as string[]).filter((n) => /^\d{4}-\d{2}-\d{2}-/.test(n) && n.slice(0, 10) >= from && n.slice(0, 10) <= to);
  const pieces = (await Promise.all(names.map((n) => rawFile("sg-content", sha, `pieces/${n}`)))).filter(Boolean).map((p: any) => ({
    id: p.id, channel: p.channel, kind: p.kind, status: p.status, publish_day: p.publish_day,
    reasons: (p.reasons ?? []).slice(-3).map((r: string) => String(r).slice(0, 240)), yt_id: p.ids?.yt_id ?? "", updated: p.updated ?? "",
    linkedin_id: p.ids?.linkedin_id ?? "" })).sort((a: any, b: any) => (a.id < b.id ? 1 : -1));
  const runsText = (await rawFile("sg-content", sha, "logs/runs.jsonl", false)) ?? "";
  const runs = runsText.trim().split("\n").slice(-12).map((l: string) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean).reverse();
  const [voice, claude, images] = await Promise.all(["voice-budget", "claude-spend", "image-spend"].map((f) => rawFile("sg-content", sha, `logs/${f}.json`)));
  return { phase: "live from GitHub", at: new Date().toISOString(), sha, today_ist: today.toISOString().slice(0, 10), github_run: "",
    pieces, runs, spend: { voice_requests: lastKeys(voice), claude: lastKeys(claude), images: lastKeys(images) } };
}

async function appsToday(sha: string) {
  const lagos = new Date(Date.now() + 3600e3).toISOString().slice(0, 10);
  const [log, schedule] = await Promise.all([rawFile("arthvan-media", sha, "logs/posts.jsonl", false), rawFile("arthvan-media", sha, "content/schedule.json")]);
  const posts = String(log ?? "").trim().split("\n").map((l) => { try { return JSON.parse(l); } catch { return null; } })
    .filter((x: any) => x && x.date === lagos)
    .map((x: any) => ({ channel: x.channel ?? (x.app ? `${x.app} reel` : "?"), item: x.item, status: x.status, at: x.at ?? "", app: x.app ?? "" }));
  const s = schedule && typeof schedule === "object" ? schedule : {};
  const item = (s.days ?? s.schedule ?? s)[lagos] ?? null;
  return { date: lagos, item: typeof item === "string" ? item : item ? JSON.stringify(item).slice(0, 80) : null, posts };
}

// The exact clock: command.clock lists each job and its Lagos minute; command.clock_due() says which are due now.
const CLOCK_REPOS: Record<string, string> = {
  "sg-content": "https://api.github.com/repos/SGULIA20/sg-content",
  "arthvan-media": "https://api.github.com/repos/SGULIA20/arthvan-media",
};

async function clock(): Promise<Response> {
  if (!Deno.env.get("GITHUB_TOKEN")) {
    await sql`update command.control set value = to_jsonb(now() + interval '10 minutes'), updated_at = now(), updated_by = 'clock'
              where key = 'clock.wait_until'`;
    return json({ started: [], waiting: "GITHUB_TOKEN is not set" });
  }
  const paused = await isPaused();
  const started: string[] = [];
  for (const job of await sql`select * from command.clock_due()`) {
    if (paused && job.repo === "sg-content") continue;                   // paused: no new sg-content runs (the engines also check)
    const claimed = await sql`update command.clock set last_fired = now()
                              where id = ${job.id} and last_fired is not distinct from ${job.last_fired} returning id`;
    if (!claimed.length) continue;                                       // another wake-up already started it
    const name = `${job.repo} ${job.workflow}`;
    try {
      await gh("POST", `/actions/workflows/${job.workflow}/dispatches`, { ref: "main", inputs: job.inputs ?? {} }, CLOCK_REPOS[job.repo]);
      started.push(name);
      if (!job.every_min) await event("clock", `started ${name}${job.note ? ` (${job.note})` : ""}`);
    } catch (e) {
      await sql`update command.clock set last_fired = ${job.last_fired} where id = ${job.id}`;   // try again next minute
      await event("error", `clock could not start ${name}: ${String(e).slice(0, 200)}`);
    }
  }
  return json({ started });
}

async function refresh(): Promise<Response> {
  const cache: Cache = ((await sql`select value from command.control where key = 'github.cache'`)[0]?.value ?? {}) as Cache;
  const live: Record<string, unknown> = { at: new Date().toISOString(), errors: [] as string[], token: !!Deno.env.get("GITHUB_TOKEN") };
  const errors = live.errors as string[];
  for (const repo of ["sg-content", "arthvan-media"]) {
    try { live[repo] = (await ghGet(`${API}/repos/SGULIA20/${repo}/actions/runs?per_page=8`, cache, { slim: slimRuns })).body; }
    catch (e) { errors.push(`${repo} runs: ${(e as Error).message}`); }
  }
  try {
    const sha = await ghGet(`${API}/repos/SGULIA20/sg-content/commits/main`, cache, { sha: true });
    const cur = (await sql`select payload->>'sha' as sha from command.status where source = 'sg-content' and key = 'snapshot'`)[0]?.sha;
    if (sha.changed || cur !== sha.body) {
      const snap = await sgSnapshot(String(sha.body));
      await sql`insert into command.status (source, key, payload) values ('sg-content', 'snapshot', ${sql.json(snap as postgres.JSONValue)})
                on conflict (source, key) do update set payload = excluded.payload, updated_at = now()`;
    }
  } catch (e) { errors.push(`sg-content files: ${(e as Error).message}`); }
  try {
    const sha = await ghGet(`${API}/repos/SGULIA20/arthvan-media/commits/main`, cache, { sha: true });
    const today = await appsToday(String(sha.body));
    await sql`insert into command.status (source, key, payload) values ('arthvan-media', 'today', ${sql.json(today as postgres.JSONValue)})
              on conflict (source, key) do update set payload = excluded.payload, updated_at = now()`;
  } catch (e) { errors.push(`arthvan-media files: ${(e as Error).message}`); }
  await sql`insert into command.status (source, key, payload) values ('github', 'runs', ${sql.json(live as postgres.JSONValue)})
            on conflict (source, key) do update set payload = excluded.payload, updated_at = now()`;
  await sql`update command.control set value = ${sql.json(cache as postgres.JSONValue)}, updated_at = now() where key = 'github.cache'`;
  return json({ ok: errors.length === 0, errors });
}

// ---------- Telegram ----------
async function tg(method: string, body: Record<string, unknown>) {
  const token = await vault("telegram_bot_token");
  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  return res.json();
}

const btn = (text: string, data: string) => ({ text, callback_data: data });

async function menu(): Promise<unknown[][]> {
  const paused = await isPaused();
  return [
    [btn(paused ? "▶️ Resume" : "⏸ Pause", paused ? "resume" : "pause"), btn("📊 Status", "status")],
    [btn("🔁 Retry failed", "retrylist"), btn("🛑 Stop running jobs", "stop?")],
    [btn("🎬 Make videos now", "run_produce"), btn("📮 Post due now", "publishlist")],
    [btn("📈 ScoreMyBiz numbers", "smb"), btn("✉️ ScoreMyBiz CEO report", "smb_ceo_report?")],
    [btn("📱 App posts now", "app_post?"), btn("💼 LinkedIn post now", "app_linkedin?")],
  ];
}

async function snapshot(): Promise<Record<string, any> | null> {
  const r = await sql`select payload, updated_at from command.status where source = 'sg-content' and key = 'snapshot'`;
  return r[0] ? { ...(r[0].payload as Record<string, any>), reported_at: r[0].updated_at } : null;
}

async function statusText(): Promise<string> {
  const s = await snapshot();
  const lines = [(await isPaused()) ? "⏸ PAUSED: nothing is made or posted until Resume." : "▶️ Running."];
  if (!s) return lines.concat("No pipeline report yet.").join("\n");
  const run = (s.runs ?? [])[0];
  if (run) lines.push(`Last run ${String(run.at).slice(0, 16).replace("T", " ")} UTC: ${run.ok ? "ok" : "CRASHED"}${run.stopped ? `, stopped: ${run.stopped}` : ""}`);
  for (const ch of CHANNELS) {
    const ps = (s.pieces ?? []).filter((p: any) => p.channel === ch);
    const today = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);          // IST date
    const ready = new Set(ps.filter((p: any) => DONE.includes(p.status) && p.publish_day > today).map((p: any) => p.publish_day));
    lines.push(`${CHANNEL_NAME[ch]}: ${ready.size} day(s) ready ahead`);
  }
  const apps = (await sql`select payload from command.status where source = 'arthvan-media' and key = 'today'`)[0]?.payload as any;
  if (apps) lines.push(`Apps today: ${(apps.posts ?? []).filter((x: any) => x.status === "published").map((x: any) => x.channel).join(", ") || "nothing posted yet"}`);
  const failed = (s.pieces ?? []).filter((p: any) => p.status.startsWith("failed") || p.status === "qa_failed");
  for (const p of failed.slice(0, 5)) lines.push(`⚠️ ${p.id}: ${p.status}`);
  return lines.join("\n");
}

async function smbText(): Promise<string> {
  const n = (await sql`select command.smb_numbers() as n`)[0].n as Record<string, any>;
  const u = n.users ?? {};
  const money = Object.entries(n.money_7d ?? {}).map(([c, v]: [string, any]) => `${c} ${v.gross} (${v.payments})`).join(", ") || "none";
  const badJobs = (n.jobs ?? []).filter((j: any) => j.status !== "ok").map((j: any) => j.name);
  return [
    "📈 ScoreMyBiz",
    `Users ${u.total ?? "?"} · paying ${u.paid ?? "?"} · trial ${u.trial ?? "?"}`,
    `New: today ${u.new_today ?? "?"}, 7 days ${u.new_7d ?? "?"} (week before ${u.new_prev_7d ?? "?"}) · active 7d ${u.active_7d ?? "?"}`,
    `Payments 7d: ${money}`,
    `Support open: ${n.support?.open ?? "?"}`,
    `App errors 24h: ${n.app_errors_24h?.total ?? "?"} (fatal ${n.app_errors_24h?.fatal ?? "?"})`,
    badJobs.length ? `⚠️ Jobs not ok: ${badJobs.join(", ")}` : "All jobs ok.",
  ].join("\n");
}

async function queueAndRun(action: string, args: Record<string, unknown>, target = "sg-content"): Promise<string> {
  const ins = await sql`insert into command.commands (target, action, args, requested_via) values (${target}, ${action}, ${sql.json(args as postgres.JSONValue)}, 'telegram') returning id`;
  const out = await run(Number(ins[0].id));                  // the trigger's own call finds the row taken and skips
  return out.state === "done" ? out.result : `Not done (${out.state}): ${out.result}`;
}

async function onCallback(data: string, chat: string, messageId: number): Promise<void> {
  const reply = async (text: string, keyboard?: unknown[][]) =>
    tg("sendMessage", { chat_id: chat, text, reply_markup: { inline_keyboard: keyboard ?? await menu() } });
  if (data === "status") return void await reply(await statusText());
  if (data === "smb") return void await reply(await smbText());
  if (data === "pause" || data === "resume") return void await reply(await queueAndRun(data, {}));
  if (data === "stop?") return void await reply("Cancel every GitHub job running right now?", [[btn("Yes, stop them", "stop"), btn("No", "menu")]]);
  if (data === "stop") return void await reply(await queueAndRun("stop", {}));
  if (data === "smb_ceo_report?") return void await reply("Build the ScoreMyBiz CEO report and email it now?", [[btn("Yes, send it", "smb_ceo_report"), btn("No", "menu")]]);
  if (data === "smb_ceo_report") return void await reply(await queueAndRun("smb_ceo_report", {}, "scoremybiz"));
  if (data === "run_produce") return void await reply(await queueAndRun("run_produce", { max: 3 }));
  if (data === "app_post?") return void await reply("Post today's ScoreMyBiz / Waypoint app posts now?", [[btn("Yes, post", "app_post"), btn("No", "menu")]]);
  if (data === "app_post") return void await reply(await queueAndRun("app_post", {}, "arthvan-media"));
  if (data === "app_linkedin?") return void await reply("Post today's LinkedIn picture post now?", [[btn("Yes, post", "app_linkedin"), btn("No", "menu")]]);
  if (data === "app_linkedin") return void await reply(await queueAndRun("app_linkedin", {}, "arthvan-media"));
  if (data === "publishlist") return void await reply("Post what is due for which channel?",
    [CHANNELS.map((c) => btn(CHANNEL_NAME[c], `publish:${c}`)), [btn("Back", "menu")]]);
  if (data.startsWith("publish:")) return void await reply(await queueAndRun("run_publish", { channel: data.slice(8) }));
  if (data === "retrylist") {
    const s = await snapshot();
    const failed = (s?.pieces ?? []).filter((p: any) => !DONE.includes(p.status) && PIECE.test(p.id)).slice(0, 6);
    if (!failed.length) return void await reply("Nothing is waiting to be retried.");
    return void await reply("Retry which one?", [...failed.map((p: any) => [btn(`${p.id} (${p.status})`, `retry:${p.id}`)]), [btn("Back", "menu")]]);
  }
  if (data.startsWith("retry:")) return void await reply(await queueAndRun("retry", { piece_id: data.slice(6) }));
  await reply("Control room:");
  void messageId;
}

async function telegramWebhook(req: Request): Promise<Response> {
  if (!same(req.headers.get("x-telegram-bot-api-secret-token") ?? "", await vault("telegram_webhook_secret"))) return json({ error: "forbidden" }, 403);
  const update = await req.json();
  const chat = await vault("telegram_chat_id");
  const cb = update.callback_query;
  if (cb) {
    if (String(cb.message?.chat?.id) !== chat) return json({ ok: true });       // only the founder's chat may steer the bot
    await tg("answerCallbackQuery", { callback_query_id: cb.id });
    await onCallback(String(cb.data ?? ""), chat, cb.message?.message_id);
    return json({ ok: true });
  }
  const msg = update.message;
  if (!msg || String(msg.chat?.id) !== chat || !msg.text) return json({ ok: true });
  const text = String(msg.text).trim();
  const word = text.split(/\s+/)[0].toLowerCase().replace(/@.*$/, "");
  if (["/start", "/menu", "/help"].includes(word)) await tg("sendMessage", { chat_id: chat, text: "Control room:", reply_markup: { inline_keyboard: await menu() } });
  else if (word === "/status") await tg("sendMessage", { chat_id: chat, text: await statusText(), reply_markup: { inline_keyboard: await menu() } });
  else if (word === "/pause" || word === "/resume") await tg("sendMessage", { chat_id: chat, text: await queueAndRun(word.slice(1), {}) });
  else await sql`insert into command.telegram_inbox (text) values (${text.slice(0, 4000)})`;   // clip confirmations etc.: the Mac inbox reads these
  return json({ ok: true });
}

async function telegramSetup(body: Record<string, unknown>): Promise<Response> {
  if (body.on === false) {
    const token = await vault("telegram_bot_token");
    if (token) await tg("deleteWebhook", {});
    await sql`update command.control set value = 'false'::jsonb, updated_at = now(), updated_by = 'setup' where key = 'telegram.webhook'`;
    return json({ webhook: false });
  }
  const token = String(body.token ?? ""), chat = String(body.chat_id ?? "");
  if (!/^\d+:[\w-]{20,}$/.test(token) || !/^-?\d+$/.test(chat)) return json({ error: "token and chat_id are required" }, 400);
  await vaultSet("telegram_bot_token", token);
  await vaultSet("telegram_chat_id", chat);
  let secret = await vault("telegram_webhook_secret");
  if (!secret) { secret = crypto.randomUUID().replaceAll("-", "") + crypto.randomUUID().replaceAll("-", ""); await vaultSet("telegram_webhook_secret", secret); }
  const set = await tg("setWebhook", { url: `${SELF}/telegram`, secret_token: secret, allowed_updates: ["message", "callback_query"], drop_pending_updates: false });
  if (!set.ok) return json({ error: `Telegram refused the webhook: ${set.description ?? "unknown"}` }, 502);
  await tg("setMyCommands", { commands: [{ command: "menu", description: "Control room buttons" }, { command: "status", description: "Pipeline status" },
    { command: "pause", description: "Pause making and posting" }, { command: "resume", description: "Resume" }] });
  await sql`update command.control set value = 'true'::jsonb, updated_at = now(), updated_by = 'setup' where key = 'telegram.webhook'`;
  await tg("sendMessage", { chat_id: chat, text: "Control room buttons are on. Tap /menu any time.", reply_markup: { inline_keyboard: await menu() } });
  return json({ webhook: true });
}

async function telegramInbox(): Promise<Response> {
  const on = (await sql`select value from command.control where key = 'telegram.webhook'`)[0]?.value === true;
  if (!on) return json({ webhook: false, messages: [] });
  const rows = await sql`update command.telegram_inbox set consumed_at = now() where consumed_at is null returning id, at, text`;
  return json({ webhook: true, messages: rows.sort((a, b) => Number(a.id) - Number(b.id)).map((r) => r.text) });
}

async function pipeline(req: Request, route: string): Promise<Response> {
  if (!same(req.headers.get("x-sg-key") ?? "", await vault("sg_command_ingest"))) return json({ error: "forbidden" }, 403);
  if (route === "control") return json({ paused: await isPaused() });
  const body = await req.json().catch(() => ({}));
  if (route === "pause") {
    await setPaused(body.paused === true, "telegram");
    return json({ paused: await isPaused() });
  }
  if (route === "telegram-setup") return await telegramSetup(body);
  if (route === "telegram-inbox") return await telegramInbox();
  // ingest
  const source = String(body.source ?? "").slice(0, 40), key = String(body.key ?? "").slice(0, 80);
  if (!source || !key) return json({ error: "source and key are required" }, 400);
  await sql`insert into command.status (source, key, payload) values (${source}, ${key}, ${sql.json(body.payload ?? {})})
            on conflict (source, key) do update set payload = excluded.payload, updated_at = now()`;
  for (const ev of (body.events ?? []).slice(0, 20)) {
    await sql`insert into command.events (source, kind, message, payload)
              values (${source}, ${String(ev.kind ?? "info").slice(0, 40)}, ${String(ev.message ?? "").slice(0, 500)}, ${sql.json(ev.payload ?? {})})`;
  }
  return json({ paused: await isPaused() });
}

Deno.serve(async (req) => {
  const route = new URL(req.url).pathname.split("/").filter(Boolean).pop() ?? "";
  try {
    if (route === "hook" && req.method === "POST") return await hook(req);
    if (route === "refresh" && req.method === "POST") {
      if (!same(req.headers.get("x-hook-secret") ?? "", await vault("sg_command_hook"))) return json({ error: "forbidden" }, 403);
      return await refresh();
    }
    if (route === "clock" && req.method === "POST") {
      if (!same(req.headers.get("x-hook-secret") ?? "", await vault("sg_command_hook"))) return json({ error: "forbidden" }, 403);
      return await clock();
    }
    if (route === "telegram" && req.method === "POST") return await telegramWebhook(req);
    if (route === "control" && req.method === "GET") return await pipeline(req, route);
    if (["ingest", "pause", "telegram-setup", "telegram-inbox"].includes(route) && req.method === "POST") return await pipeline(req, route);
    return json({ error: "not found" }, 404);
  } catch (e) {
    console.error(e);
    return json({ error: "internal error" }, 500);
  }
});
