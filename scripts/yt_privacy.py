"""One-off: list a channel's uploads whose title contains a text, and optionally set all of them except one to private (never deleted).
python scripts/yt_privacy.py sglearning|arthvan "Kumbhalgarh" KEEP_ID [--apply]
Without --apply it only lists. Private videos can be made public again in YouTube Studio."""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import youtube  # noqa: E402

DATA = "https://www.googleapis.com/youtube/v3"


def main(argv) -> int:
    channel, text, keep = argv[0], argv[1].lower(), argv[2]
    apply = "--apply" in argv
    tok = youtube.access_token(channel, os.environ)
    _s, _h, ch = youtube.call("GET", f"{DATA}/channels?part=contentDetails&mine=true", tok)
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], ""
    while True:
        _s, _h, body = youtube.call("GET", f"{DATA}/playlistItems?part=contentDetails,snippet&maxResults=50&playlistId={uploads}" + (f"&pageToken={page}" if page else ""), tok)
        ids += [(i["contentDetails"]["videoId"], i["snippet"]["title"]) for i in body.get("items", []) if text in i["snippet"]["title"].lower()]
        page = body.get("nextPageToken", "")
        if not page:
            break
    _s, _h, st = youtube.call("GET", f"{DATA}/videos?part=status,snippet&id={','.join(i for i, _t in ids)}", tok) if ids else (0, 0, {"items": []})
    for v in st.get("items", []):
        print(f"{v['id']} | {v['status']['privacyStatus']} | publish {v['status'].get('publishAt', '-')} | {v['snippet']['title'][:70]}", flush=True)
    if keep not in dict(ids):
        print(f"KEEP id {keep} was not found in the matches; nothing changed", flush=True)
        return 1
    targets = [i for i, _t in ids if i != keep]
    print(f"keep {keep}; {len(targets)} to make private", flush=True)
    if not apply:
        print("dry run: nothing changed", flush=True)
        return 0
    for vid in targets:
        body = json.dumps({"id": vid, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}).encode()
        req = urllib.request.Request(f"{DATA}/videos?part=status", data=body, method="PUT",
                                     headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        urllib.request.urlopen(req, context=youtube.secrets.ssl_context()).read()
        print(f"{vid} set to private", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
