"""News cards drawn in code for the news Reels (founder, 30 Oct 2026: "use graphics made internally by claude with zero cost" for the Top 10
and the 3-4 daily breaking-news Reels). One card per scene: a tag, a big icon, the number and a few plain words; the narration's
captions run underneath as usual. No picture model is called, so a news Reel costs only its voice and its script."""
import re

ACCENT = {"ai": "#7C5CFF", "tech": "#3BA4FF", "crypto": "#F7931A", "markets": "#22C55E", "economy": "#FFD166", "jobs": "#FF6B6B",
          "companies": "#3BA4FF", "commodities": "#FFB703", "money": "#FFD166", "world": "#EF476F", "numbers": "#FFD166"}
ICONS = [("bitcoin", "🪙"), ("crypto", "🪙"), ("hack", "🕵️"), ("ai ", "🤖"), ("google", "🔍"), ("chip", "💾"), ("oil", "🛢️"),
         ("crude", "🛢️"), ("gold", "🥇"), ("silver", "🥈"), ("rupee", "💱"), ("rupaya", "💱"), ("dollar", "💵"), ("job", "💼"),
         ("layoff", "📦"), ("naukri", "💼"), ("bank", "🏦"), ("loan", "🏦"), ("emi", "🏦"), ("tax", "🧾"), ("gira", "📉"), ("fall", "📉"),
         ("upar", "📈"), ("badh", "📈"), ("china", "🌏"), ("america", "🌎"), ("us ", "🌎"), ("japan", "🌏"), ("sip", "🌱"),
         ("phone", "📱"), ("car", "🚗"), ("ev", "🔋"), ("startup", "🚀"), ("ipo", "🔔"), ("price", "🏷️"), ("daam", "🏷️")]
NUMBER = re.compile(r"(?:[$₹]\s?)?\d[\d,.]*\s?(?:%|percent|crore|lakh|billion|million|trillion|bn)?", re.I)


def icon_for(text: str) -> str:
    blob = f" {text.lower()} "
    return next((emoji for word, emoji in ICONS if word in blob), "📰")


def data(scene: dict, index: int, total: int, category: str, roundup: bool) -> dict:
    """What the card shows: the writer's card block when given, else drawn from the narration."""
    card = ((scene.get("visual") or {}).get("card") or {}) if (scene.get("visual") or {}).get("type") == "card" else {}
    vo = str(scene.get("vo") or "")
    num = card.get("big_number")
    if num is None:
        m = NUMBER.search(vo)
        num = m.group(0).strip() if m else ""
    line = card.get("line") or " ".join(re.sub(r"[^\w\s%₹$.,]", "", vo).split()[:6])
    if roundup and 0 < index < total - 1:
        tag = f"#{index}"
    else:
        tag = card.get("tag") or ("BREAKING" if index == 0 else category.upper())
    cat = category if category in ACCENT else "money"
    return {"tag": tag, "icon": card.get("icon") or icon_for(vo), "big_number": num, "line": line, "accent": ACCENT[cat],
            "glow": ACCENT[cat] + "55"}
