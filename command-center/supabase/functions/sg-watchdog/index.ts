// sg-watchdog: tells the founder on Telegram when the clock is not doing its job (founder, 24 Oct 2026).
//   POST /   (x-hook-secret = Vault sg_command_hook; pg_cron every 10 minutes via command.watchdog_tick())
// Two checks, each problem told once (command.watchdog_seen):
//   - a clock job 30 minutes late (command.clock_late(): the clock did not start it)
//   - a failed GitHub run of a workflow the clock starts, in sg-content or arthvan-media
// Separate from sg-command on purpose: if sg-command breaks, this still speaks. Reads only; starts nothing.
import postgres from "npm:postgres@3.4.5";

const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, { prepare: false, max: 1 });
const REPOS: Record<string, string> = {
  "sg-content": "https://api.github.com/repos/SGULIA20/sg-content",
  "arthvan-media": "https://api.github.com/repos/SGULIA20/arthvan-media",
};
const FAILED = ["failure", "timed_out", "startup_failure"];

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

// True the first time a key is seen; false after that, so each problem is told once.
async function fresh(key: string): Promise<boolean> {
  return (await sql`insert into command.watchdog_seen (key) values (${key}) on conflict do nothing returning key`).length > 0;
}

const wat = (t: Date) => t.toLocaleTimeString("en-GB", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit" });

async function lateJobs(): Promise<string[]> {
  const out: string[] = [];
  for (const j of await sql`select * from command.clock_late()`) {
    if (await fresh(j.key)) out.push(`⏰ ${j.repo} ${j.workflow} did not start (due ${wat(new Date(j.due))} WAT)${j.note ? ` - ${j.note}` : ""}`);
  }
  return out;
}

async function failedRuns(): Promise<string[]> {
  const token = Deno.env.get("GITHUB_TOKEN");
  if (!token) return [];
  const start = (await sql`select (value #>> '{}')::timestamptz as t from command.control where key = 'watchdog.since'`)[0]?.t;
  const since = new Date(Math.max(Date.now() - 6 * 3600_000, start ? new Date(start).getTime() : 0)).toISOString().slice(0, 19) + "Z";
  const watched = new Set((await sql`select distinct repo, workflow from command.clock where enabled`).map((r) => `${r.repo}/${r.workflow}`));
  const out: string[] = [];
  for (const [repo, base] of Object.entries(REPOS)) {
    const res = await fetch(`${base}/actions/runs?status=completed&per_page=50&created=>=${since}`, {
      headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json", "x-github-api-version": "2022-11-28" },
    });
    if (!res.ok) { out.push(`⚠️ watchdog could not read ${repo} runs (GitHub ${res.status})`); continue; }
    for (const r of (await res.json()).workflow_runs ?? []) {
      const file = String(r.path ?? "").split("/").pop();
      if (!FAILED.includes(r.conclusion) || !watched.has(`${repo}/${file}`)) continue;
      if (await fresh(`run:${r.id}`)) out.push(`❌ ${repo} ${file} failed (${r.conclusion}, started ${wat(new Date(r.run_started_at ?? r.created_at))} WAT): ${r.html_url}`);
    }
  }
  return out;
}

Deno.serve(async (req) => {
  try {
    if (req.method !== "POST") return json({ error: "method" }, 405);
    if (!same(req.headers.get("x-hook-secret") ?? "", await vault("sg_command_hook"))) return json({ error: "forbidden" }, 403);
    const lines = [...await lateJobs(), ...await failedRuns()];
    if (lines.length) {
      const text = ["Watchdog:", ...lines].join("\n").slice(0, 3900);
      await sql`insert into command.events (source, kind, message) values ('sg-watchdog', 'error', ${text})`;
      const token = await vault("telegram_bot_token"), chat = await vault("telegram_chat_id");
      if (token && chat) {
        await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ chat_id: chat, text, disable_web_page_preview: true }),
        });
      }
    }
    return json({ told: lines.length });
  } catch (e) {
    return json({ error: String(e).slice(0, 300) }, 500);
  }
});
