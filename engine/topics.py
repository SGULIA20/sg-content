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
    # jobs, companies and AI (founder, 29 Oct 2026, "C"); a dead feed is skipped, never fatal
    ("ET Jobs", "https://economictimes.indiatimes.com/jobs/rssfeeds/107115.cms", 3),
    ("ET Tech", "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms", 2),
    ("Mint Companies", "https://www.livemint.com/rss/companies", 2),
]
HOUSEHOLD = ["emi", "petrol", "diesel", "tax", "salary", "sip", "price", "prices", "inflation", "loan", "fd ", "epf",
             "pension", "gold", "rupee", "gst", "mutual fund", "upi", "deposit", "insurance", "home loan", "rent", "repo rate",
             "interest rate", "fuel", "crude", "oil", "sensex", "nifty", "market", "stock", "share", "profit", "results", "ipo",
             "crore", "lakh", "jobs", "layoff", "income", "subsidy", "scam", "fraud", "fine", "penalty"]
# The viewer's own wallet (founder, 24 Oct 2026): on 21-24 Oct the Shorts about dividends, US stocks for 1 dollar and petrol prices
# reached about 1,300-1,500 people each on Instagram; the one about Meta's AI spending reached 59. Market words still count, less.
WALLET = ["emi", "petrol", "diesel", "tax", "salary", "sip", "price", "prices", "inflation", "loan", "fd ", "epf", "pension", "gold",
          "rupee", "gst", "mutual fund", "upi", "deposit", "insurance", "home loan", "rent", "repo rate", "interest rate", "fuel",
          "income", "subsidy", "scam", "fraud", "dividend", "savings", "credit card", "lpg", "electricity", "ticket", "fees"]
# Jobs and the workplace are as personal as the wallet (founder, 29 Oct 2026: "550 Indian employees fired after lunch break")
JOBS = ["layoff", "laid off", "lays off", "fired", "job cuts", "jobs cut", "sacked", "hiring", "appraisal", "salary hike", "pay cut",
        "notice period", "resign", "work from office", "ai jobs", "replace jobs", "employees"]
NUMBER = re.compile(r"\d|lakh|crore|%|\$")
BANNED_TOPIC = ["modi", "rahul gandhi", "bjp", "congress", "election", "rally", "pakistan", "minister", "parliament",
                "opposition", "cm ", "pm ",
                # stock-tip headlines: the writer can only turn them into tips, which the gate rejects (22 Oct 2026: three wasted drafts)
                "stocks in news", "stocks to buy", "stocks to watch", "top picks", "buy or sell", "target price", "multibagger",
                "stock recommendations", "hot stocks", "stocks in focus", "shares to buy"]
# market plumbing nobody at home needs: auctions, operations notices, securities results. Never a Short on its own.
PLUMBING = ["variable rate repo", "vrr", "money market operations", "auction", "government securities", "state government securities",
            "treasury bill", "t-bill", "laf", "omo ", "switch auction", "conversion/switch", "sdl", "g-sec", "under laf"]
FRESH_HOURS = 24
# A buffered Short posts up to a week later (founder, 30 Oct 2026: "today, 22 Oct" Shorts posted on 25-27 Oct reached 3-15 people):
# headlines tied to a day go only to the same-day news Short (engine.news), never into the buffer.
DATED = ["today", "tomorrow", "this week", "live", "outlook", "prediction", "expiry", "opening bell", "closing bell", "schedule",
         "trade setup", "market wrap", "what to expect", "ahead of"]
DATE_IN_TITLE = re.compile(r"\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)
# the daily market call is crowded and goes stale by evening: not even the news Short takes it
MARKET_CALL = ["outlook", "prediction", "expiry", "trade setup", "opening bell", "closing bell", "market wrap", "technical view"]


def dated(item: dict) -> bool:
    title = str(item.get("title", ""))
    return any(w in title.lower() for w in DATED) or bool(DATE_IN_TITLE.search(title))
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
    return any(k in blob for k in HOUSEHOLD + WALLET + JOBS)


def score(item: dict) -> int:
    blob = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    if any(b in blob for b in BANNED_TOPIC):
        return -10
    if any(p in blob for p in PLUMBING):
        return -5
    s = item.get("rank", 0)
    if NUMBER.search(blob):
        s += 3
    if any(k in blob for k in WALLET) or any(k in blob for k in JOBS):
        s += 4
    elif any(k in blob for k in HOUSEHOLD):
        s += 1
    return s


def pick_finance(items: list, used_links: set, now: datetime, news: bool = False, hours: int = FRESH_HOURS) -> dict | None:
    """The best household money story of the last `hours`. For the buffer (news=False) a headline tied to a day is skipped;
    for the same-day news Short (news=True) it is welcome, but the daily market call never is."""
    fresh = [i for i in items if i.get("published") and now - i["published"] <= timedelta(hours=hours)
             and i["link"] not in used_links and score(i) > 0 and household(i)
             and (not any(w in str(i.get("title", "")).lower() for w in MARKET_CALL) if news else not dated(i))]
    if not fresh:
        return None
    return max(fresh, key=lambda i: (score(i), i["published"]))


def load_myth_bank(root: Path = CONTENT_DIR) -> list:
    return yaml.safe_load((Path(root) / "myth-topics.yaml").read_text()) or []


def load_long_bank(root: Path = CONTENT_DIR) -> list:
    return yaml.safe_load((Path(root) / "long-topics.yaml").read_text()) or []


def next_long_finance(root: Path, used_ids: set) -> dict:
    """Evergreen subject for a 12-minute finance documentary: the bank in order, each once, then the rotation restarts."""
    bank = load_long_bank(root)
    for t in bank:
        if t["id"] not in used_ids:
            return t
    return bank[0]


def next_myth(root: Path, used_ids: set) -> dict:
    """The next unused topic; a famous, visual place (`priority: 1` in the bank) goes first (founder, 24 Oct 2026: Ram Setu reached
    1,564 on Instagram, Kailash's 'who climbed it' question 71; places people already know and can picture travel further)."""
    bank = load_myth_bank(root)
    fresh = [t for t in bank if t["id"] not in used_ids]
    if fresh:
        return max(fresh, key=lambda t: (t.get("priority", 0), -bank.index(t)))
    return bank[0]                                                 # every topic used once: start the rotation again
