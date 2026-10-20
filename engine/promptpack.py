"""Prompt packs for the Gemini app: one presenter part per scene in the founder's locked format (docs/spec-gemini-clips.md §1).

write(piece)  -> parts (Claude turns the script into narration ≤ 18 words + a scene prompt per part)
render(piece, parts) -> the pack text to paste
send(piece, text) -> Telegram + Desktop/SG-Content-Project/Packs/<id>.txt, status awaiting-clips
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import pieces, secrets, telegram, writer
from .config import ROOT
from .pieces import Piece

MAX_WORDS = 18
PACKS_DIR = Path.home() / "Desktop" / "SG-Content-Project" / "Packs"
WATERMARK = "@SGLearning watermark top right, white, bold, 80% opacity."
LOCKED = ("SG — 30-year-old Indian man, warm brown skin, short dark hair, medium beard, navy blazer over white t-shirt, dark jeans, "
          "white sneakers, glowing blue holographic tablet floating beside him. Charismatic expressive presenter: animated face, confident "
          "hand gestures, dynamic body language, engaging eye contact with camera — energy of a sharp explainer talking to a friend. "
          "Speaks Hinglish naturally.")
LOGO_WORDS = re.compile(r"\b(logo|logos|emblem|emblems|brand mark|trademark)\b", re.IGNORECASE)
SYSTEM = """You turn a finished Hinglish video script into a PROMPT PACK for Google's Gemini video generator, one part per scene, in exactly this JSON shape:
{"parts": [{"part": 1, "scene": 0, "narration": "...", "prompt": "..."}]}

Rules for narration: the exact words the presenter SG speaks in that part, Hinglish in Latin script, AT MOST 18 WORDS (the generator cuts longer lines); keep every number from the scene's `vo` as digits; keep the finance disclaimer line where the script has it.
Rules for prompt: one vivid shot description in English, 20-45 words: where SG [locked] is, what the floating tablet shows (short text only, like "₹30,213 CRORE" or "8.15%"), his mood and gesture, light and camera move. Always write "SG [locked]" for the presenter. NEVER name a real company, brand, logo, emblem, politician or real person in the visual; use plain labels ("BIMA", "IPO", "BANK"). No text other than the tablet label. Keep the bottom quarter of the frame clear.
Mood: hook = high energy leaning in; explanation = confident teacher; "aapke liye" = sincere, slower; disclaimer = calm; closing question = grin, point at camera, slow nod.
Return only the JSON."""


def _trim(narration: str) -> str:
    words = narration.split()
    if len(words) <= MAX_WORDS:
        return narration.strip()
    cut = " ".join(words[:MAX_WORDS])
    m = list(re.finditer(r"[.?!]", cut))
    if m and m[-1].end() > len(cut) * 0.5:
        return cut[: m[-1].end()].strip()
    return cut.rstrip(",;:") + "."


def write(piece: Piece, client=None, spend: Path = writer.SPEND_FILE) -> list:
    import anthropic
    client = client or anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    aspect = "9:16 vertical" if piece.kind == "short" else "16:9 cinematic"
    user = json.dumps({"aspect": aspect, "channel": piece.channel, "script": piece.script}, ensure_ascii=False, indent=1)
    response = client.beta.messages.create(
        model=writer.MODEL, max_tokens=8000, output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        system=[{"type": "text", "text": SYSTEM + "\n\nLOCKED CHARACTER LINE (write it as SG [locked] in prompts):\n" + LOCKED,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Aspect: {aspect}\n\nSCRIPT:\n{user}"}])
    writer.record_spend(response.usage, spend)
    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
    data = json.loads(writer.FENCE.sub("", text.strip()))
    parts = []
    for i, p in enumerate(data.get("parts", [])):
        parts.append({"part": int(p.get("part") or i + 1), "scene": int(p.get("scene") if p.get("scene") is not None else i),
                      "narration": _trim(str(p.get("narration", ""))), "prompt": str(p.get("prompt", "")).strip()})
    return parts


def _clean_prompt(prompt: str) -> str:
    cleaned = LOGO_WORDS.sub("plain label", prompt)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned.endswith("."):
        cleaned += "."
    return cleaned + " No logos, no real-company marks, no text except the tablet label."


def render(piece: Piece, parts: list) -> str:
    aspect = "9:16 vertical" if piece.kind == "short" else "16:9 cinematic"
    title = (piece.script or {}).get("captions", {}).get("youtube", {}).get("title", piece.id)
    out = [f"PROMPT PACK — {piece.id} — {title}", "",
           'LOCKED CHARACTER LINE (paste as "SG [locked]" in every prompt):', LOCKED, "",
           f"Every prompt: {aspect}, with the watermark line as written in each prompt. Leave the bottom 25% of the frame clear for captions. Generate the parts in order; each part is one clip of about 10 seconds.", ""]
    for p in parts:
        out += [f"Part {p['part']} — scene {p['scene'] + 1}",
                f"Narration: \"{p['narration']}\"",
                f"Prompt: {aspect}. {_clean_prompt(p['prompt'])} {WATERMARK}", ""]
    out += ["Drop the clips into Downloads in order. The bot will file them and send you a contact sheet; reply \"ok " + piece.id + "\"."]
    return "\n".join(out)


def send(piece: Piece, text: str, packs_dir: Path = PACKS_DIR, root: Path = ROOT, notify=telegram.send) -> Path:
    packs_dir = Path(packs_dir)
    packs_dir.mkdir(parents=True, exist_ok=True)
    path = packs_dir / f"{piece.id}.txt"
    path.write_text(text)
    piece.topic["pack_sent"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pieces.save(pieces.transition(piece, "awaiting-clips"), root)
    notify(f"Prompt pack ready: {piece.id}\nFile: {path}\n\n{text}"[:4000])
    return path
