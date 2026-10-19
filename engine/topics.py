"""Topic sources: finance news from RSS/Atom feeds and press pages, mythology from the hand-written topic bank (spec §3 step 1)."""
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

from . import secrets
from .config import CONTENT_DIR

FEEDS = [
    ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", 3),
    ("ET Economy", "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", 3),
    ("Mint Markets", "https://www.livemint.com/rss/markets", 3),
    ("Business Standard Markets", "https://www.business-standard.com/rss/markets-106.rss", 2),
    ("RBI Press Releases", "https://www.rbi.org.in/pressreleases_rss.xml", 5),
    ("SEBI Press", "https://www.sebi.gov.in/sebirss.xml", 5),
    ("PIB Finance", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", 4),
]
HOUSEHOLD = ["emi", "petrol", "diesel", "tax", "salary", "sip", "price", "prices", "inflation", "loan", "fd ", "epf",
             "pension", "gold", "rupee", "gst", "mutual fund", "upi", "deposit", "insurance", "home loan", "rent", "repo rate",
             "interest rate", "fuel", "crude", "oil", "sensex", "nifty", "market", "stock", "share", "profit", "results", "ipo",
             "crore", "lakh", "jobs", "layoff", "income", "subsidy", "scam", "fraud", "fine", "penalty"]
NUMBER = re.compile(r"\d|lakh|crore|%|\$")
BANNED_TOPIC = ["modi", "rahul gandhi", "bjp", "congress", "election", "rally", "pakistan", "minister", "parliament",
                "opposition", "cm ", "pm "]
FRESH_HOURS = 24
NS = {"atom": "http://www.w3.org/2005/Atom"}


def _text(el, *names):
    for n in names:
        found = el.find(n)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def _when(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def parse_feed(raw: bytes, source: str, rank: int) -> list:
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):                                   # RSS 2.0
        items.append({"title": _text(it, "title"), "link": _text(it, "link"), "summary": re.sub(r"<[^>]+>", "", _text(it, "description")),
                      "published": _when(_text(it, "pubDate")), "source": source, "rank": rank})
    for en in root.iter("{http://www.w3.org/2005/Atom}entry"):   # Atom
        link_el = en.find("atom:link", NS)
        items.append({"title": _text(en, "atom:title".replace("atom:", "{http://www.w3.org/2005/Atom}")),
                      "link": (link_el.get("href") if link_el is not None else "") or "",
                      "summary": _text(en, "{http://www.w3.org/2005/Atom}summary"),
                      "published": _when(_text(en, "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published")),
                      "source": source, "rank": rank})
    return [i for i in items if i["title"] and i["link"]]


def fetch_feed(name: str, url: str, rank: int, fetch=None) -> list:
    fetch = fetch or (lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sg-content/1.0"}),
                                                       timeout=30, context=secrets.ssl_context()).read())
    try:
        return parse_feed(fetch(url), name, rank)
    except Exception as e:                                          # one dead feed never stops the run
        print(f"feed {name} failed: {type(e).__name__}", flush=True)
        return []


def fetch_all(fetch=None) -> list:
    out = []
    for name, url, rank in FEEDS:
        out += fetch_feed(name, url, rank, fetch)
    return out


def household(item: dict) -> bool:
    blob = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return any(k in blob for k in HOUSEHOLD)


def score(item: dict) -> int:
    blob = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    if any(b in blob for b in BANNED_TOPIC):
        return -10
    s = item.get("rank", 0)
    if NUMBER.search(blob):
        s += 3
    if any(k in blob for k in HOUSEHOLD):
        s += 2
    return s


def pick_finance(items: list, used_links: set, now: datetime) -> dict | None:
    fresh = [i for i in items if i.get("published") and now - i["published"] <= timedelta(hours=FRESH_HOURS)
             and i["link"] not in used_links and score(i) > 0 and household(i)]
    if not fresh:
        return None
    return max(fresh, key=lambda i: (score(i), i["published"]))


def load_myth_bank(root: Path = CONTENT_DIR) -> list:
    return yaml.safe_load((Path(root) / "myth-topics.yaml").read_text()) or []


def next_myth(root: Path, used_ids: set) -> dict:
    bank = load_myth_bank(root)
    for t in bank:
        if t["id"] not in used_ids:
            return t
    return bank[0]                                                 # every topic used once: start the rotation again
