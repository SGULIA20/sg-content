"""Numbers in a Hinglish script and whether each one is backed by the fact sheet or the standing claims library (spec §6.1).

numbers_in("do hazaar paanch sau") -> [2500.0]; match() returns the numbers that have no source (empty list = pass).
"""
import re
from datetime import date
from pathlib import Path

import yaml

from .config import CONTENT_DIR, today_ist

UNITS = {
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "chah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "terah": 13, "chaudah": 14, "pandrah": 15,
    "solah": 16, "satrah": 17, "atharah": 18, "unnees": 19, "bees": 20, "pachees": 25, "tees": 30, "chalees": 40,
    "pachaas": 50, "sattar": 70, "assi": 80, "nabbe": 90,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}
# "saath" (60) is left out on purpose: it also means "with" (ke saath) and would invent numbers.
SCALES = {"sau": 100, "सौ": 100, "hazaar": 1000, "hazar": 1000, "हज़ार": 1000, "हजार": 1000,
          "lakh": 100_000, "laakh": 100_000, "लाख": 100_000, "crore": 10_000_000, "karod": 10_000_000, "करोड़": 10_000_000}
PERCENT = {"pratishat", "प्रतिशत", "percent", "%"}
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?%?|%|[\u0900-\u097F]+|[^\W\d_]+", re.UNICODE)
YEAR_RANGE = (1900, 2100)
SMALL_COUNT = 10


def _extract(text: str) -> list:
    """List of (value, unit) where unit is 'pct', 'scale' or None."""
    text = text.translate(DEVANAGARI_DIGITS).replace("₹", " ")
    out, cur, total, unit, active = [], 0.0, 0.0, None, False

    def flush():
        nonlocal cur, total, unit, active
        if active:
            out.append((total + cur, unit))
        cur, total, unit, active = 0.0, 0.0, None, False

    for tok in TOKEN.findall(text):
        low = tok.lower()
        if low == "%" or (low[-1:] == "%" and low[:-1].replace(",", "").replace(".", "").isdigit()):
            if low != "%":
                flush(); cur, active = float(low[:-1].replace(",", "")), True
            if active:
                unit = "pct"
            flush(); continue
        if low[0].isdigit():
            flush(); cur, active = float(low.replace(",", "")), True; continue
        if low in UNITS:
            if active and cur:
                flush()                      # two unit words in a row ("ek do teen") are separate numbers
            cur, active = float(UNITS[low]), True   # after a scale word (hazaar ...) the unit continues the compound
            continue
        if low in SCALES:
            if not active:
                cur, active = 1.0, True
            scale = SCALES[low]
            if scale == 100:
                cur = (cur or 1) * 100
            elif cur:
                total += cur * scale; cur = 0.0
            else:
                total = (total or 1) * scale
            unit = unit or "scale"
            continue
        if low in PERCENT:
            if active:
                unit = "pct"
            flush(); continue
        flush()
    flush()
    return out


def numbers_in(text: str) -> list:
    return [v for v, _u in _extract(text)]


UNIT_SCALES = {"crore": 10_000_000, "karod": 10_000_000, "lakh": 100_000, "laakh": 100_000, "thousand": 1000, "hazaar": 1000,
               "k": 1000, "million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000}


def _known_values(entries: list) -> list:
    """Every fact number as written and scaled by the words in its unit ("24400 crore INR" also means 2.44e11)."""
    out = []
    for f in entries:
        for field in ("text", "quote"):                       # every number in the sourced sentence, not only the headline one
            out += numbers_in(str(f.get(field) or ""))        # (25 Oct 2026: "11 percent" and "10,000 INR" sat in the text, not in `number`)
        n = f.get("number")
        if n is None:
            continue
        n = float(n)
        out.append(n)
        scale = 1
        for word in re.findall(r"[a-z]+", str(f.get("unit") or "").lower()):
            scale *= UNIT_SCALES.get(word, 1)
        if scale != 1:
            out.append(n * scale)
    return out


ABOUT = re.compile(r"\b(lagbhag|karib|kareeb|takreeban|taqreeban|approx|about|around|roughly|se zyada|se kam|se upar|se neeche|लगभग|करीब)\b", re.IGNORECASE)
ROUND_TOL = 0.10
ERA = re.compile(r"\b(BCE|BC|CE|AD|ईसा पूर्व|ईस्वी|isa poorv|isvi)\b", re.IGNORECASE)


def _about_positions(text: str) -> list:
    return [m.end() for m in ABOUT.finditer(text)]


INDEX_NAME = re.compile(r"\b(nifty(?:\s+(?:next|midcap|smallcap|bank|it|auto|pharma|fmcg|metal|realty|psu bank))?|sensex|bse|s&p)\s*$", re.IGNORECASE)


def _index_name_before(text: str, pos: int) -> bool:
    """"Nifty 50", "Nifty 500 TRI", "BSE 100": the number is part of an index's name, not a claim."""
    return bool(INDEX_NAME.search(text[max(0, pos - 30):pos]))


YEAR_DASH = re.compile(r"\b1\d{3}\s*[-–]\s*$|\b20\d{2}\s*[-–]\s*$")


def match(script_text: str, facts: list, library: list, tolerance: float = 0.005, context: tuple = ()) -> list:
    """`context`: the topic's own words (its title); a number the topic itself names ("500 rupaye ki SIP") is the subject, not a claim."""
    known = _known_values(list(facts) + list(library)) + [v for c in context for v in numbers_in(str(c or ""))]
    unmatched = []
    abouts = _about_positions(script_text)
    eras = [m.start() for m in ERA.finditer(script_text)]
    for value, unit, pos in _extract_with_pos(script_text):
        if _index_name_before(script_text, pos):
            continue
        if unit is None and float(value).is_integer() and 1 <= value <= 3500 and any(0 <= e - pos <= 14 for e in eras):
            continue                                  # "3102 BCE", "1010 CE", "1200 ईसा पूर्व": a date, not a claim
        tol = ROUND_TOL if any(0 <= pos - a <= 25 for a in abouts) else tolerance      # "lagbhag 7 crore": 10 % slack within 25 chars of the word
        if unit is None and value < SMALL_COUNT and float(value).is_integer():
            continue                                  # counters: teen cheezein, do baatein
        if unit is None and YEAR_RANGE[0] <= value <= YEAR_RANGE[1] and float(value).is_integer():
            continue                                  # a year, not a claim
        if unit is None and float(value).is_integer() and value < 100 and YEAR_DASH.search(script_text[max(0, pos - 8):pos]):
            continue                                  # "1920-21": the end of a year range
        if any(abs(value - k) <= tol * max(abs(k), 1) for k in known):
            continue
        unmatched.append(value)
    return unmatched


def _extract_with_pos(text: str) -> list:
    """(value, unit, char position of the first token of the number) by re-running the extractor per token span."""
    out, values = [], _extract(text)
    positions = [m.start() for m in TOKEN.finditer(text.translate(DEVANAGARI_DIGITS).replace("₹", " "))
                 if m.group(0)[0].isdigit() or m.group(0).lower() in UNITS or m.group(0).lower() in SCALES]
    for i, (v, u) in enumerate(values):
        out.append((v, u, positions[i] if i < len(positions) else 0))
    return out


def load_library(root: Path = CONTENT_DIR, today: date | None = None) -> list:
    entries = yaml.safe_load((Path(root) / "claims.yaml").read_text()) or []
    today = today or today_ist()
    return [e for e in entries if not e.get("valid_until") or date.fromisoformat(str(e["valid_until"])) >= today]
