// sg-command: the founder control room's only door to GitHub, ScoreMyBiz and the Telegram bot.
//   POST /hook             a new row in command.commands (sent by the database trigger, x-hook-secret)
//   POST /ingest           a pipeline reports its status (x-sg-key = Vault sg_command_ingest); answers {paused}
//   GET  /control          a pipeline asks whether it is paused (x-sg-key)
//   POST /pause            Telegram /pause and /resume keep the shared flag in step (x-sg-key)
//   POST /telegram         the bot's webhook (x-telegram-bot-api-secret-token = Vault telegram_webhook_secret)
//   POST /telegram-setup   {token, chat_id, on}: store the bot in Vault and switch the webhook on or off (x-sg-key)
//   POST /telegram-inbox   messages that are not commands, for the Mac inbox (x-sg-key); answers {webhook, messages}
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

async function gh(method: string, path: string, body?: unknown) {
  const token = Deno.env.get("GITHUB_TOKEN");
  if (!token) throw new Error("GITHUB_TOKEN is not set on the sg-command function");
  const res = await fetch(GH + path, {
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
    if (route === "telegram" && req.method === "POST") return await telegramWebhook(req);
    if (route === "control" && req.method === "GET") return await pipeline(req, route);
    if (["ingest", "pause", "telegram-setup", "telegram-inbox"].includes(route) && req.method === "POST") return await pipeline(req, route);
    return json({ error: "not found" }, 404);
  } catch (e) {
    console.error(e);
    return json({ error: "internal error" }, 500);
  }
});
