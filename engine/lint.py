"""Gates on the written piece before anything is voiced or posted (spec §4, §6.3-6.8). Pure functions, no I/O except load_lists."""
import re
from pathlib import Path

import yaml

from .config import CONTENT_DIR, is_story, story_words
from .pieces import Piece

DISCLAIMER = "Yeh investment advice nahi hai"
MYTH_LABELS = {"scripture", "archaeology", "disputed", "legend"}
FINANCE_LABELS = {"reported", "official", "analyst-view"}
SHORT_WORDS = (90, 135)          # measured 20 Oct 2026: the clone speaks Hinglish at ~2.5 words/s; 135 words + pads ≈ 58 s
LONG_WORDS_PER_MIN = 140
AVATAR_MAX_SHARE = 0.25
SIMILARITY_MAX = 0.6
TITLE_MAX, IG_CAPTION_MAX, THREADS_MAX = 60, 2200, 500
IG_TAGS = (5, 8)
SHARE = re.compile(r"\b(share|bhejo|bhej do|tag karo|forward)\b", re.I)
BIG_NUMBER_MAX = 12
PHONE = re.compile(r"(\+?\d[\d\s\-]{8,}\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


HOOK_WORDS_MAX = 12              # the first spoken line decides whether people stay (founder, 25 Oct 2026); Hinglish needs ke/ka/hai
SLOW_OPENING = re.compile(r"^\W*(subah|raat|shaam|dopahar|aaj|kal|ek din|ek baar|budhvaar|somvaar|mangalvaar|guruvaar|shukravaar|shanivaar|"
                          r"ravivaar|january|february|march|april|may|june|july|august|september|october|november|december|"
                          r"results ka din|bhai|papa|mummy|beta|beti|behen|wife)\b", re.I)


def check_hook(piece: Piece) -> list:
    """Shorts open on the claim or the question: short, concrete, not a scene being set."""
    s = piece.script or {}
    hook = str(s.get("hook") or "").strip()
    first = str(((s.get("scenes") or [{}])[0]).get("vo") or "").strip()
    out = []
    if not hook:
        return ["hook: missing"]
    words = len(re.findall(r"\d[\d,.]*|[^\W\d_]+", hook))           # "5,000" is one word
    if words > HOOK_WORDS_MAX:
        out.append(f"hook: {words} words, at most {HOOK_WORDS_MAX}")
    if SLOW_OPENING.search(hook):
        out.append("hook: opens by setting a scene (a time, a day or a character); open on the claim or the question")
    if not ("?" in hook or re.search(r"\d", hook) or re.search(r"\s[A-Z]", hook)):
        out.append("hook: needs a question, a number or a name")
    if first and re.findall(r"\w+", first.lower())[:4] != re.findall(r"\w+", hook.lower())[:4]:
        out.append("hook: the first spoken line must start with the hook")
    return out


OPENER_SIMILAR = 0.35            # first pictures this alike look like a repeat to the viewer (founder, 25 Oct 2026)
CAST = ("bhai", "papa", "mummy", "beta", "beti", "behen", "wife", "sg", "bank uncle", "shopkeeper")
PHONE_WORDS = re.compile(r"\b(phone|screen|mobile|notification)\b", re.I)


SEND = re.compile(r"\b(bhejo|bhej do|bhejiye)\b", re.I)
SEND_WORDS_MAX = 14


def check_send(piece: Piece) -> list:
    """A Short ends by naming who to send it to: sends are Instagram's strongest signal for new viewers (founder, 25 Oct 2026)."""
    if piece.kind != "short":
        return []
    s = piece.script or {}
    line = str(s.get("end_question") or "").strip()
    scenes = s.get("scenes") or []
    last = str((scenes[-1] if scenes else {}).get("vo") or "")
    out = []
    if not SEND.search(line):
        out.append("send: the Short must end with who to send it to ('... ko bhejo, jo ...')")
    elif len(re.findall(r"\w+", line)) > SEND_WORDS_MAX:
        out.append(f"send: the send line is longer than {SEND_WORDS_MAX} words")
    elif not SEND.search(last):
        out.append("send: the last spoken scene must say the send line")
    return out


def check_opener(piece: Piece, recent: list) -> list:
    """The first picture is the thumbnail of the scroll: never a cast member staring at a phone, never close to the last Shorts' openers.
    `recent`: [(piece id, first-scene picture prompt)] of the same channel's last Shorts."""
    scenes = (piece.script or {}).get("scenes") or []
    prompt = str(((scenes[0] if scenes else {}).get("visual") or {}).get("prompt") or "")
    if not prompt or piece.kind != "short":
        return []
    out = []
    low = prompt.lower()
    if PHONE_WORDS.search(low) and any(re.search(rf"\b{c}\b", low) for c in CAST):
        out.append("opener: the first picture is a cast member with a phone again; open on the story's own object or moment")
    for pid, other in recent:
        if similarity(prompt, other) >= OPENER_SIMILAR:
            out.append(f"opener: the first picture is too close to {pid}'s; pick a different subject")
            break
    return out


_BANNED = None


def load_lists(root: Path = CONTENT_DIR) -> tuple:
    global _BANNED
    banned = yaml.safe_load((Path(root) / "banned.yaml").read_text())
    tags = yaml.safe_load((Path(root) / "hashtags.yaml").read_text())
    _BANNED = banned
    return banned, tags


def _tokens(text: str) -> set:
    return set(re.findall(r"[\wऀ-ॿ]+", text.lower()))


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def script_text(piece: Piece) -> str:
    s = piece.script or {}
    return " ".join([s.get("hook", "")] + [sc.get("vo", "") for sc in s.get("scenes", [])] + [s.get("end_question", "")])


def _phrase_re(phrase: str) -> re.Pattern:
    """Whole-phrase match: 'modi' must not hit 'commodity'. Word characters include Devanagari."""
    return re.compile(r"(?<![\w\u0900-\u097F])" + re.escape(phrase.strip().lower()) + r"(?![\w\u0900-\u097F])", re.IGNORECASE)


def _banned_hits(text: str, banned: dict, sections: list) -> list:
    out = []
    for section in sections:
        for phrase in banned.get(section, []):
            if _phrase_re(phrase).search(text):
                out.append(f"{section}: {phrase.strip()}")
    return out


def all_text(piece: Piece) -> str:
    """Everything the audience can read: script, captions, tags, cards (gates run over all of it)."""
    s = piece.script or {}
    c = s.get("captions", {})
    yt, ig, th = c.get("youtube", {}), c.get("instagram", {}), c.get("threads", {})
    cards = [f"{x.get('big_number', '')} {x.get('line', '')}" for x in s.get("cards", [])]
    cards += [f"{v['card'].get('big_number', '')} {v['card'].get('line', '')}" for v in (sc.get("visual") or {} for sc in s.get("scenes", [])) if v.get("card")]
    return " \n ".join([script_text(piece), yt.get("title", ""), yt.get("description", ""), " ".join(yt.get("tags", [])),
                        ig.get("caption", ""), th.get("text", ""), *cards])


JARGON = ["free cash flow", "cash flow", "capex", "liquidation", "liquidated", "leverage", "ebitda", "basis point", "bps", "bear market",
          "bull market", "hyperscaler", "valuation", "market cap", "guidance", "yield", "open interest", "derivative", "fii", "dii",
          "q1 ", "q2 ", "q3 ", "q4 ", "eps", "headwind", "tailwind", "macro", "fiscal deficit"]     # founder, 30 Oct 2026: plain words only


def jargon_hits(piece: Piece) -> list:
    """Money and tech jargon in the spoken lines of a Learning with SG Short; each must be said in plain words instead."""
    if piece.channel != "sglearning" or piece.kind != "short":
        return []
    spoken = " " + " ".join(sc.get("vo", "") for sc in (piece.script or {}).get("scenes", [])).lower() + " "
    found = [j.strip() for j in JARGON if re.search(r"(?<![a-z])" + re.escape(j.strip()) + r"(?![a-z])", spoken)]
    return [f"jargon: say {', '.join(found)} in everyday words (founder: a 15-year-old must follow it)"] if found else []


def check_script(piece: Piece, banned: dict, prior_scripts: list) -> list:
    reasons = []
    s = piece.script or {}
    scenes = s.get("scenes", [])
    text = script_text(piece)
    reasons += _banned_hits(text, banned, ["politics", "communal", "advice"])
    reasons += jargon_hits(piece)
    if piece.channel == "arthvan":
        reasons += _banned_hits(text, banned, ["myth_forbidden"])
        for i, sc in enumerate(scenes):
            if sc.get("label") not in MYTH_LABELS and sc.get("facts_used"):      # a scene that states a fact must say what kind of evidence it is
                reasons.append(f"label: scene {i} has no evidence label")
    if piece.channel == "sglearning" and piece.kind == "short" and DISCLAIMER.lower() not in text.lower():
        reasons.append("disclaimer: finance script must speak the disclaimer line")
    words = len(re.findall(r"[\wऀ-ॿ]+", " ".join(sc.get("vo", "") for sc in scenes)))
    if piece.kind == "short":
        lo, hi = story_words(piece.channel, piece.topic) if is_story(piece.channel, piece.kind) else SHORT_WORDS
    else:
        target = int(piece.topic.get("target_minutes") or 15) * LONG_WORDS_PER_MIN
        lo, hi = int(target * 0.8), int(target * 1.2)
    if not lo <= words <= hi:
        reasons.append(f"length: {words} words, allowed {lo}-{hi}")
    if piece.kind == "short":
        reasons += check_hook(piece)
    if scenes:
        share = sum(1 for sc in scenes if (sc.get("visual") or {}).get("type") == "avatar") / len(scenes)
        if share > AVATAR_MAX_SHARE:
            reasons.append(f"avatar: {share:.0%} of scenes, cap {AVATAR_MAX_SHARE:.0%}")
    for prior in prior_scripts:
        if similarity(text, prior) >= SIMILARITY_MAX:
            reasons.append("originality: too close to an earlier script")
            break
    return reasons


def check_captions(piece: Piece, hashtags: dict) -> list:
    reasons = []
    c = (piece.script or {}).get("captions", {})
    yt, ig, th = c.get("youtube", {}), c.get("instagram", {}), c.get("threads", {})
    allowed = hashtags.get(piece.channel, {})
    banned = load_lists()[0] if _BANNED is None else _BANNED
    public = all_text(piece)[len(script_text(piece)):]
    reasons += _banned_hits(public, banned, ["politics", "communal", "advice"] + (["myth_forbidden"] if piece.channel == "arthvan" else []))
    if len(yt.get("title", "")) > TITLE_MAX:
        reasons.append(f"title: {len(yt['title'])} chars, max {TITLE_MAX}")
    if len(ig.get("caption", "")) > IG_CAPTION_MAX:
        reasons.append("instagram: caption too long")
    if piece.channel == "sglearning" and DISCLAIMER.lower() not in ig.get("caption", "").lower():
        reasons.append("disclaimer: Instagram caption must carry the disclaimer")
    if not SHARE.search(ig.get("caption", "")):
        reasons.append("share: Instagram caption needs one share line (share karo / bhejo) naming who to send it to")
    tags = ig.get("hashtags", [])
    if not IG_TAGS[0] <= len(tags) <= IG_TAGS[1]:
        reasons.append(f"hashtags: {len(tags)} Instagram tags, need {IG_TAGS[0]}-{IG_TAGS[1]}")
    unknown = [t for t in tags if t not in allowed.get("instagram", [])]
    if unknown:
        reasons.append(f"hashtags: not in the allowed list: {', '.join(unknown)}")
    if len(th.get("text", "")) > THREADS_MAX:
        reasons.append(f"threads: {len(th['text'])} chars, max {THREADS_MAX}")
    s = piece.script or {}
    bigs = [c.get("big_number", "") for c in s.get("cards", [])] + [(sc.get("visual") or {}).get("card", {}).get("big_number", "") for sc in s.get("scenes", []) if (sc.get("visual") or {}).get("card")]
    for b in bigs:
        if len(b) > BIG_NUMBER_MAX:
            reasons.append(f"card: big_number '{b}' is {len(b)} characters, max {BIG_NUMBER_MAX}")
    for name, blob in (("youtube", yt.get("description", "") + yt.get("title", "")), ("instagram", ig.get("caption", "")), ("threads", th.get("text", ""))):
        if PHONE.search(blob) or EMAIL.search(blob):
            reasons.append(f"pii: phone number or email in {name} text")
    return reasons
