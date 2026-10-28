"""Post one review sample as an Instagram Trial Reel (founder, 28 Oct 2026: "upload now this sample on Instagram as trial reel").

    python scripts/post_sample.py logs/review/gold-motion-sample.mp4 2026-10-30-sglearning-short

The video is fetched from main on GitHub; the caption is that piece's own Instagram caption. The result goes to logs/review/samples.jsonl."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import instagram, pieces, secrets  # noqa: E402
from engine.config import ROOT  # noqa: E402


def main(argv: list) -> int:
    video, piece_id = argv[0], argv[1]
    piece = pieces.load(piece_id, ROOT)
    token, ig_id = secrets.get("IG_ACCESS_TOKEN"), secrets.get("IG_USER_ID")
    url = f"https://raw.githubusercontent.com/{instagram.DEFAULT_REPO}/main/{video}"
    params = {"media_type": "REELS", "video_url": url, "caption": instagram.caption_text(piece),
              "thumb_offset": str(instagram.THUMB_OFFSET_MS), "trial_params": json.dumps({"graduation_strategy": instagram.TRIAL_GRADUATION})}
    reel = instagram._create_and_publish(ig_id, token, params, "trial reel", instagram.call, time.sleep)
    link = instagram.call("GET", f"/{reel}", token, {"fields": "permalink"}).get("permalink", "")
    row = {"at": datetime.now(timezone.utc).isoformat(), "video": video, "piece": piece_id, "reel": reel, "permalink": link, "trial": True}
    with (ROOT / "logs" / "review" / "samples.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
