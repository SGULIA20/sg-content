"""Monthly refresh of the Instagram and Threads long-lived tokens; expiry dates to logs/tokens.json; rotated secrets stored via gh when ACTIONS_PAT exists.

python -m engine.tokens --refresh
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from . import instagram, secrets, telegram, threads
from .config import ROOT

SECRET_FOR = {"IG_ACCESS_TOKEN": ("instagram_expires", instagram.refresh_token), "THREADS_ACCESS_TOKEN": ("threads_expires", threads.refresh_token)}


def refresh(env=None, root: Path = ROOT, today: date | None = None, ig_refresh=instagram.refresh_token, th_refresh=threads.refresh_token) -> dict:
    """Returns {secret name: new token} for every token that refreshed; writes expiry dates (and errors) to logs/tokens.json."""
    today = today or date.today()
    env = os.environ if env is None else env
    path = Path(root) / "logs" / "tokens.json"
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    data["errors"] = []
    new = {}
    for name, fn in (("IG_ACCESS_TOKEN", ig_refresh), ("THREADS_ACCESS_TOKEN", th_refresh)):
        key = SECRET_FOR[name][0]
        try:
            out = fn(secrets.get(name, env))
            token = out.get("access_token")
            seconds = int(out.get("expires_in", 60 * 86400))
            if token:
                secrets.remember(token)
                new[name] = token
            data[key] = (today + timedelta(seconds=seconds)).isoformat()
        except Exception as e:
            data["errors"].append(f"{name}: {secrets.scrub(str(e))[:160]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    return new


def store(new: dict, env=None) -> list:
    """Writes rotated tokens into the repo's Actions secrets with gh (needs ACTIONS_PAT). Returns the names stored."""
    env = os.environ if env is None else env
    pat, repo = env.get("ACTIONS_PAT"), env.get("GITHUB_REPOSITORY", instagram.DEFAULT_REPO)
    if not pat or not new:
        return []
    done = []
    for name, value in new.items():
        r = subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value, text=True, env={**os.environ, "GH_TOKEN": pat})
        if r.returncode == 0:
            done.append(name)
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args(argv)
    if not a.refresh:
        ap.print_help(); return 1
    new = refresh()
    stored = store(new)
    data = json.loads((ROOT / "logs" / "tokens.json").read_text())
    msg = [f"Token refresh: refreshed {sorted(new)}, stored in GitHub secrets {stored or 'nothing (no ACTIONS_PAT)'}",
           f"Instagram expires {data.get('instagram_expires', '?')}, Threads expires {data.get('threads_expires', '?')}"]
    missing = [n for n in new if n not in stored]
    if missing:
        msg.append(f"ACTION: update the GitHub secret(s) {missing} by re-authorising, or add ACTIONS_PAT so this runs by itself.")
    if data.get("errors"):
        msg.append("ERRORS: " + "; ".join(data["errors"]))
    telegram.send("\n".join(msg))
    print("\n".join(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
