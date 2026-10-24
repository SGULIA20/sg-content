"""Read-only Google Play Console reports for the founder's apps, through a read-only service account (22 Oct 2026).

The account `play-reports-reader` can only "view app information and download bulk reports": it cannot change a listing, a price or a release.
Its key file is ~/sg-content/play-reader-key.json (git-ignored). No third-party library: the sign-in is a standard RS256 JWT signed with openssl.

    python -m engine.playreports --probe        list what the account can see
    python -m engine.playreports --summary      installs, ratings and store-performance numbers per app
"""
import base64
import csv
import os
import io
import json
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import secrets
from .config import ROOT

KEY_FILE = ROOT / "play-reader-key.json"
DEVELOPER_ID = "4994467858870216610"                # Arthvan Analytics Private Limited, shown on the Play Console home page
BUCKETS = (f"pubsite_prod_rev_{DEVELOPER_ID}", f"pubsite_prod_{DEVELOPER_ID}")
APPS = {"scoremybiz": "com.scoremybiz.app", "waypoint": "com.arthvananalytics.waypoint"}
SCOPE_STORAGE = "https://www.googleapis.com/auth/devstorage.read_only"
SCOPE_PUBLISHER = "https://www.googleapis.com/auth/androidpublisher"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class PlayError(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(message: bytes, private_key_pem: str) -> bytes:
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(private_key_pem)
        path = f.name
    try:
        Path(path).chmod(0o600)
        out = subprocess.run(["openssl", "dgst", "-sha256", "-sign", path], input=message, capture_output=True, check=True)
        return out.stdout
    finally:
        Path(path).unlink(missing_ok=True)


def _load_key(key_file: Path) -> dict:
    """The key file on the Mac, or PLAY_READER_KEY_B64 (the same file, base64) in the cloud."""
    if Path(key_file).exists():
        return json.loads(Path(key_file).read_text())
    b64 = os.environ.get("PLAY_READER_KEY_B64", "")
    if not b64:
        raise PlayError("no Play reader key: neither play-reader-key.json nor PLAY_READER_KEY_B64 is present")
    secrets.remember(b64)
    return json.loads(base64.b64decode(b64))


def access_token(scope: str, key_file: Path = KEY_FILE, post=None) -> str:
    key = _load_key(key_file)
    now = int(time.time())
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({"iss": key["client_email"], "scope": scope, "aud": TOKEN_URL, "iat": now, "exp": now + 3000}).encode())
    signing_input = f"{head}.{claims}".encode()
    jwt = f"{head}.{claims}.{_b64(_sign(signing_input, key['private_key']))}"
    form = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt}).encode()
    req = urllib.request.Request(TOKEN_URL, data=form, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with (post or (lambda r: urllib.request.urlopen(r, timeout=60, context=secrets.ssl_context())))(req) as r:
            tok = json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        raise PlayError(f"token request failed ({e.code}): {secrets.scrub(e.read().decode(errors='replace'))[:200]}") from None
    secrets.remember(tok)
    return tok


def _get(url: str, token: str, opener=None) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with (opener or (lambda r: urllib.request.urlopen(r, timeout=120, context=secrets.ssl_context())))(req) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise PlayError(f"HTTP {e.code} for {url.split('?')[0]}: {secrets.scrub(e.read().decode(errors='replace'))[:200]}") from None


def list_objects(bucket: str, prefix: str, token: str) -> list:
    out, page = [], ""
    while True:
        url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o?prefix={urllib.parse.quote(prefix)}&maxResults=1000" + (f"&pageToken={page}" if page else "")
        data = json.loads(_get(url, token))
        out += [o["name"] for o in data.get("items", [])]
        page = data.get("nextPageToken", "")
        if not page:
            return out


def read_csv(bucket: str, name: str, token: str) -> list:
    raw = _get(f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{urllib.parse.quote(name, safe='')}?alt=media", token)
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def find_bucket(token: str) -> tuple:
    """(bucket, first objects) for the first bucket name the account can list."""
    last = ""
    for b in BUCKETS:
        try:
            return b, list_objects(b, "stats/", token)[:20]
        except PlayError as e:
            last = str(e)
    raise PlayError(last)


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip() or 0)
    except ValueError:
        return 0.0


def _col(row: dict, *names) -> str:
    for n in names:
        for k in row:
            if k.strip().lower() == n.lower():
                return row[k]
    return ""


def summarise(app: str, installs: list, countries: list, ratings: list, store: list, days: int = 28) -> str:
    """Plain-text numbers for one app from the monthly report rows (each list is CSV rows, dates as YYYY-MM-DD)."""
    def last(rows):
        rows = sorted(rows, key=lambda r: _col(r, "Date"))
        return rows[-days:]
    lines = [f"{app}"]
    inst = last(installs)
    if inst:
        new = sum(_num(_col(r, "Daily Device Installs")) for r in inst)
        gone = sum(_num(_col(r, "Daily Device Uninstalls")) for r in inst)
        active = _num(_col(inst[-1], "Active Device Installs"))
        lines.append(f"  installs {new:.0f}, uninstalls {gone:.0f}, active devices {active:.0f} (last {len(inst)} days)")
    if countries:
        by = {}
        cut = _col(last(installs)[0], "Date") if inst else ""
        for r in countries:
            if cut and _col(r, "Date") < cut:
                continue
            c = _col(r, "Country") or "?"
            by[c] = by.get(c, 0) + _num(_col(r, "Daily Device Installs"))
        top = sorted(((v, c) for c, v in by.items() if v > 0), reverse=True)[:5]
        if top:
            lines.append("  by country: " + ", ".join(f"{c} {v:.0f}" for v, c in top))
    rat = sorted(ratings, key=lambda r: _col(r, "Date"))
    if rat:
        lines.append(f"  rating {_num(_col(rat[-1], 'Total Average Rating')):.2f} stars")
    st = last(store)
    if st:
        vis = sum(_num(_col(r, "Store Listing Visitors", "Store listing visitors")) for r in st)
        acq = sum(_num(_col(r, "Store Listing Acquisitions", "Store listing acquisitions", "Installers")) for r in st)
        if vis:
            lines.append(f"  listing visitors {vis:.0f}, acquisitions {acq:.0f}, conversion {100 * acq / vis:.1f}%")
    return "\n".join(lines)


def _latest_files(objs: list, pkg: str, kind: str, suffix: str, months: int = 2) -> list:
    """Newest `months` monthly files, e.g. stats/installs/installs_<pkg>_202610_overview.csv."""
    want = [o for o in objs if o.startswith(f"stats/{kind}/") and f"_{pkg}_" in o and o.endswith(suffix)]
    return sorted(want)[-months:]


def fetch_rows(tok: str, bucket: str = BUCKETS[1]) -> dict:
    objs = list_objects(bucket, "stats/", tok)
    data = {}
    for app, pkg in APPS.items():
        def rows(kind, suffix, pkg=pkg):
            r = []
            for name in _latest_files(objs, pkg, kind, suffix):
                r += read_csv(bucket, name, tok)
            return r
        data[app] = {"installs": rows("installs", "_overview.csv"), "countries": rows("installs", "_country.csv"), "ratings": rows("ratings", "_overview.csv"),
                     "store": rows("store_performance", "_overview.csv") or rows("store_performance", "_country.csv")}
    return data


def summary_text(data: dict) -> str:
    return "Google Play, last 28 days (read-only reports)\n\n" + "\n\n".join(
        summarise(app, d["installs"], d["countries"], d["ratings"], d["store"]) for app, d in data.items())


def fetch_summary(tok: str, bucket: str = BUCKETS[1]) -> str:
    return summary_text(fetch_rows(tok, bucket))


def gates_text(data: dict, gates: dict) -> str:
    """Where Waypoint stands against the founder's phase gates, and which two countries lead for each app."""
    lines = []
    wp = gates.get("waypoint_plus", {})
    inst = sorted(data.get("waypoint", {}).get("installs", []), key=lambda r: _col(r, "Date"))
    active = _num(_col(inst[-1], "Active Device Installs")) if inst else 0
    need = _num(wp.get("active_installs", 0))
    open_checks = [k for k, v in (wp.get("manual") or {}).items() if not v]
    lines.append(f"Waypoint Plus gate: active installs {active:.0f} of {need:.0f}; {len(open_checks)} checks open"
                 + (": " + ", ".join(k.replace("_", " ") for k in open_checks) if open_checks else ""))
    top_n = int(gates.get("focus_markets_per_app", 2))
    for app, d in data.items():
        by = {}
        for r in d.get("countries", []):
            by[_col(r, "Country") or "?"] = by.get(_col(r, "Country") or "?", 0) + _num(_col(r, "Daily Device Installs"))
        lead = sorted(((v, c) for c, v in by.items() if v > 0), reverse=True)[:top_n]
        if lead:
            lines.append(f"Focus markets for {app}: " + ", ".join(f"{c} ({v:.0f} installs)" for v, c in lead))
    return "\n".join(lines)


def weekly_text(tok: str, gates_path: Path = ROOT / "content" / "growth-gates.yaml") -> str:
    import yaml
    data = fetch_rows(tok)
    gates = yaml.safe_load(Path(gates_path).read_text()) if Path(gates_path).exists() else {}
    return summary_text(data) + "\n\n" + gates_text(data, gates)


STATE = ROOT / "logs" / "growth.json"


def _week(today=None) -> str:
    from datetime import date
    y, w, _d = (today or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--weekly" in argv:
        from . import telegram
        week = _week()
        done = json.loads(STATE.read_text()) if STATE.exists() else {}
        if done.get("sent") == week and "--force" not in argv:
            print(f"{week}: already sent")
            return 0
        try:
            text = weekly_text(access_token(SCOPE_STORAGE))
        except PlayError as e:                           # access not open yet: stay quiet, try again next slot
            print(f"Play reports not readable yet: {str(e)[:160]}")
            return 0
        print(text)
        if "--send" in argv and telegram.send(text):
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"sent": week}))
        return 0
    tok = access_token(SCOPE_STORAGE)
    if "--summary" in argv:
        from . import telegram
        text = fetch_summary(tok)
        print(text)
        if "--send" in argv:
            print("telegram:", telegram.send(text))
        return 0
    print("signed in as the read-only reader: ok")
    bucket, objs = find_bucket(tok)
    print("bucket:", bucket)
    for o in objs:
        print("  ", o)
    return 0


if __name__ == "__main__":
    sys.exit(main())
