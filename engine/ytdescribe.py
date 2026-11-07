"""Prints title, length, publish time and the start of the description of given YouTube videos (read-only), to write distinct titles for near-duplicates.

python -m engine.ytdescribe arthvan ID,ID,...
"""
import sys

from . import youtube
from .youtube import call

API = "https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,status&id="


def describe(token: str, ids: list, call=call) -> list:
    status, _h, body = call("GET", API + ",".join(ids), token)
    if status != 200:
        return [{"error": status}]
    return [{"id": v["id"], "title": v["snippet"]["title"], "duration": v["contentDetails"]["duration"], "publishAt": v["status"].get("publishAt", ""),
             "description": v["snippet"].get("description", "")} for v in body.get("items", [])]


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    channel, ids = args[0], [i.strip() for i in args[1].split(",") if i.strip()]
    for v in describe(youtube.access_token(channel), ids):
        print(f"--- {v.get('id')} | {v.get('title')} | {v.get('duration')} | {v.get('publishAt')}\n{str(v.get('description', ''))[:700]}\n", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
