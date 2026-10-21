// sg-command: the founder control room's only door to GitHub.
//   POST /hook     a new row in command.commands (sent by the database trigger, x-hook-secret)
//   POST /ingest   a pipeline reports its status (x-sg-key = Vault sg_command_ingest); answers {paused}
//   GET  /control  a pipeline asks whether it is paused (x-sg-key)
//   POST /pause    Telegram /pause and /resume keep the shared flag in step (x-sg-key)
// Only the actions below exist; anything else is rejected and recorded.
import postgres from "npm:postgres@3.4.5";

const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, { prepare: false, max: 1 });
const GH = "https://api.github.com/repos/SGULIA20/sg-content";
const CHANNELS = ["sglearning", "arthvan"];
const KINDS = ["short", "long"];
const PIECE = /^\d{4}-\d{2}-\d{2}-(sglearning|arthvan)-(short|long)$/;
const WORKFLOWS = ["produce.yml", "publish.yml"];

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
    default:
      throw new Rejected(`unknown action "${action}"`);
  }
}

async function hook(req: Request): Promise<Response> {
  if (!same(req.headers.get("x-hook-secret") ?? "", await vault("sg_command_hook"))) return json({ error: "forbidden" }, 403);
  const { id } = await req.json();
  const rows = await sql`update command.commands set state = 'sent' where id = ${id} and state = 'queued' returning *`;
  if (!rows.length) return json({ ok: true, skipped: true });
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
  return json({ ok: state === "done", state, result });
}

async function pipeline(req: Request, route: string): Promise<Response> {
  if (!same(req.headers.get("x-sg-key") ?? "", await vault("sg_command_ingest"))) return json({ error: "forbidden" }, 403);
  if (route === "control") return json({ paused: await isPaused() });
  const body = await req.json();
  if (route === "pause") {
    await setPaused(body.paused === true, "telegram");
    return json({ paused: await isPaused() });
  }
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
    if (route === "control" && req.method === "GET") return await pipeline(req, route);
    if ((route === "ingest" || route === "pause") && req.method === "POST") return await pipeline(req, route);
    return json({ error: "not found" }, 404);
  } catch (e) {
    console.error(e);
    return json({ error: "internal error" }, 500);
  }
});
