"""One Monday report (founder, 24 Nov 2026: "Merge Monday's three reports into one"). The weekly report, "what's working" and the
post-mortem each sent their own Telegram message within a minute of each other, and the first two covered the same week's numbers.
They now write their text to a folder (SG_REPORT_DIR) and say nothing; this module reads the three and sends ONE message.

Claude is asked to merge them: every number that matters once, no repetition, the one change for the week last. If Claude cannot be
reached, the three are joined and each cut to fit, so the report still arrives as a single message.

python -m engine.monday [--dry]
"""
import os
import sys
from pathlib import Path

from . import secrets

MODEL = "claude-opus-5-5"
PARTS = (("report", "LAST WEEK IN NUMBERS"), ("whatworks", "WHAT WORKED"), ("postmortem", "POST-MORTEM AND LESSONS"))
ROOM = 3800                              # Telegram cuts a message at 4,096 characters
PROMPT = """Three automatic reports about the same week of two YouTube channels (Learning with SG and SG-MYTH-WORLD) follow. Their owner
wants ONE message on Telegram instead of three. Merge them:

- Plain text for Telegram, no markdown tables, at most {room} characters.
- Order: a one-line headline of the week; then each channel in turn (subscribers, views and watch hours, best and weakest video with
  the reason); then what the post-mortem learned (the lessons given to the writers, shortest form); then anything not read or missing;
  last, on its own line, "This week's one change:" with the single most important change.
- Every figure appears once. Where two reports give the same figure, keep one. Where they disagree, show both and say so.
- Use only what is in the three reports: no new numbers, no advice of your own. Keep any warning that numbers could not be read.

{reports}"""


def collect(folder: Path) -> dict:
    out = {}
    for name, _title in PARTS:
        try:
            text = (Path(folder) / f"{name}.txt").read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            out[name] = text
    return out


def joined(parts: dict) -> str:
    """The three one after another under their headings, each cut so the whole fits one message (the fallback)."""
    if not parts:
        return ""
    each = (ROOM - 60 * len(parts)) // len(parts)
    blocks = []
    for name, title in PARTS:
        if name in parts:
            body = parts[name]
            blocks.append(f"— {title} —\n" + (body if len(body) <= each else body[:each - 20].rstrip() + "\n… (cut to fit)"))
    return "\n\n".join(blocks)


def _ask(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    r = client.messages.create(model=MODEL, max_tokens=8000, messages=[{"role": "user", "content": prompt}])
    try:
        from . import writer
        writer.record_spend(r.usage, writer.SPEND_FILE, None)
    except Exception:
        pass
    return "".join(getattr(b, "text", "") for b in r.content).strip()


def merge(parts: dict, ask=_ask) -> str:
    if len(parts) < 2:                                                # one report needs no merging
        return joined(parts)
    reports = "\n\n".join(f"===== {title} =====\n{parts[name]}" for name, title in PARTS if name in parts)
    try:
        text = ask(PROMPT.format(room=ROOM - 200, reports=reports[:40000]))
        if len(text) < 200:
            raise ValueError("the merged report is too short to be right")
        return text[:ROOM]
    except Exception as e:
        print(f"monday: Claude did not merge the reports ({type(e).__name__}: {secrets.scrub(str(e))[:120]})", flush=True)
        return joined(parts)


def run(folder: Path, ask=_ask, notify=None, dry: bool = False) -> str:
    parts = collect(folder)
    if not parts:
        print("monday: no report was written this week", flush=True)
        return ""
    text = "📊 Monday report\n\n" + merge(parts, ask)
    missing = [title.lower() for name, title in PARTS if name not in parts]
    if missing:
        text += "\n\n(Not made this week: " + ", ".join(missing) + ".)"
    if not dry:
        if notify is None:
            from . import telegram
            notify = telegram.send
        notify(text[:4000])
    return text


def hold(name: str, text: str) -> bool:
    """Called by the three reports: True when the text was put aside for the one Monday message (so the caller sends nothing)."""
    folder = os.environ.get("SG_REPORT_DIR")
    if not folder:
        return False
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / f"{name}.txt").write_text(text, encoding="utf-8")
    return True


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    folder = os.environ.get("SG_REPORT_DIR")
    if not folder:
        print("SG_REPORT_DIR is not set: nothing to merge")
        return 0
    print(run(Path(folder), dry="--dry" in args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
