"""Caption cues per scene (phrases of up to six words, timed by syllable weight) and the ASS file that burns them in (spec §3 step 8)."""
import re

MAX_WORDS = 6
FONT = "Noto Sans Devanagari"
DEV_CONSONANT = re.compile(r"[क-हक़-य़]")
DEV_VIRAMA = "्"
DEV_VOWEL = re.compile(r"[अ-औ]")
LAT_VOWELS = re.compile(r"[aeiouy]+", re.I)


def syllables(word: str) -> int:
    if re.search(r"[ऀ-ॿ]", word):
        n = len(DEV_VOWEL.findall(word))
        for m in DEV_CONSONANT.finditer(word):
            nxt = word[m.end():m.end() + 1]
            if nxt != DEV_VIRAMA:
                n += 1
        return max(1, n)
    if word.strip().isdigit():
        return max(1, len(word.strip()))
    return max(1, len(LAT_VOWELS.findall(word)))


def _phrases(text: str) -> list:
    words = text.split()
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= MAX_WORDS or w.endswith((",", ".", "?", "!", ":", ";", "।")):
            out.append(" ".join(cur)); cur = []
    if cur:
        if out and len(cur) <= 2:
            out[-1] = out[-1] + " " + " ".join(cur)
            if len(out[-1].split()) > MAX_WORDS:            # keep the limit even after merging a tail
                words2 = out[-1].split(); out[-1] = " ".join(words2[:MAX_WORDS]); out.append(" ".join(words2[MAX_WORDS:]))
        else:
            out.append(" ".join(cur))
    return out or [text]


def split(vo: str, seconds: float) -> list:
    """[(start, end, text)] covering 0..seconds, time shared by syllable count."""
    phrases = _phrases(vo.strip())
    weights = [sum(syllables(w) for w in p.split()) for p in phrases]
    total = float(sum(weights)) or 1.0
    cues, t = [], 0.0
    for i, (p, w) in enumerate(zip(phrases, weights)):
        end = seconds if i == len(phrases) - 1 else t + seconds * w / total
        cues.append((round(t, 3), round(end, 3), p))
        t = end
    return cues


def offset(cues: list, by: float) -> list:
    return [(round(s + by, 3), round(e + by, 3), t) for s, e, t in cues]


def _ts(sec: float) -> str:
    h = int(sec // 3600); m = int(sec % 3600 // 60); s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass(cues: list, size: tuple) -> str:
    w, h = size
    portrait = h > w
    font_size = 64 if portrait else 54
    margin_v = int(h * 0.22) if portrait else int(h * 0.08)
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,{font},{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,{mv},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ).format(w=w, h=h, font=FONT, fs=font_size, mv=margin_v)
    lines = [f"Dialogue: 0,{_ts(s)},{_ts(e)},Default,,0,0,0,,{t.replace(chr(10), ' ')}" for s, e, t in cues]
    return head + "\n".join(lines) + "\n"
