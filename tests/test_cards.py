import struct
import zlib

import pytest

from engine import cards

pytestmark = pytest.mark.slow


def _png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _nonbg_share(path, bg=(11, 15, 26), tol=40):
    """Share of pixels that differ from the background colour (decoded with zlib, no PIL dependency)."""
    data = path.read_bytes()
    pos, chunks, w, h = 8, [], 0, 0
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8]); body = data[pos + 8:pos + 8 + ln]; pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10]); assert depth == 8 and ctype in (2, 6)
            bpp = 3 if ctype == 2 else 4
        elif typ == b"IDAT":
            chunks.append(body)
    raw = zlib.decompress(b"".join(chunks)); stride = w * bpp; out = bytearray(); prev = bytearray(stride); i = 0
    for _y in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0; b = prev[x]; c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line; prev = line
    n = w * h; diff = 0
    for k in range(0, len(out), bpp * 97):           # sample every 97th pixel
        r, g, b = out[k], out[k + 1], out[k + 2]
        if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > tol:
            diff += 1
    return diff / (n / 97)


def test_number_card_is_1080x1920_png(tmp_path):
    out = cards.render("number", {"big_number": "88%", "line": "tel import hota hai", "source": "PPAC, Apr 2025"}, tmp_path / "n.png", (1080, 1920))
    assert _png_size(out) == (1080, 1920)


def test_thumb_is_1280x720(tmp_path):
    out = cards.render("thumb", {"words": ["OIL", "₹100", "EMI?"], "number": "100$"}, tmp_path / "t.png", (1280, 720))
    assert _png_size(out) == (1280, 720)


def test_devanagari_renders_no_tofu(tmp_path):
    out = cards.render("hook", {"line": "₹80 हज़ार करोड़ का सवाल"}, tmp_path / "h.png", (1080, 1920))
    assert _nonbg_share(out) > 0.02


def test_slide_and_label_and_source_sizes(tmp_path):
    assert _png_size(cards.render("slide", {"big_number": "₹2,500", "line": "x", "source": "RBI"}, tmp_path / "s.png", (1080, 1350))) == (1080, 1350)
    assert _png_size(cards.render("label", {"label": "archaeology"}, tmp_path / "l.png", (400, 90))) == (400, 90)
    assert _png_size(cards.render("source", {"name": "Economic Times", "date": "19 Oct 2026"}, tmp_path / "src.png", (1080, 120))) == (1080, 120)
    assert _png_size(cards.render("end", {"question": "Aapko kya lagta hai?", "handle": "@sanjeev_gulia"}, tmp_path / "e.png", (1080, 1920))) == (1080, 1920)


def test_unknown_kind_raises(tmp_path):
    with pytest.raises(KeyError):
        cards.render("banner", {}, tmp_path / "x.png", (10, 10))
