"""
bharatNova: daily Marathi agriculture knowledge + bharatNova product ads.
Makes animated Reels (Marathi female + male voice, zoom in / zoom out), single posts and swipe carousels,
posts them to Instagram and ALWAYS adds one comment under every new post.

    python bharatnova.py --kind reel_agri             # daily agri-knowledge Reel
    python bharatnova.py --kind reel_ad               # product ad Reel (needs products.json)
    python bharatnova.py --kind carousel              # agri-knowledge carousel (7 slides)
    python bharatnova.py --kind post                  # single agri tip post
    python bharatnova.py --kind product_carousel      # product carousel
    python bharatnova.py --kind product_post          # single product post
    python bharatnova.py --kind evening               # picks by weekday (ad reel / product carousel / product post)
    python bharatnova.py --kind noon                  # carousel on even days, post on odd days
    add --dry-run to build only, --sample to test the look (no AI, no voice), --topic "..." to force a topic
"""
import argparse
import asyncio
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

VERSION = "bharatnova v2 (Marathi, Sarvam/Gemini/edge voices, Devanagari voice text, Ken Burns zoom)"
BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
ASSETS = BASE / "assets"
HANDLE = (os.getenv("IG_HANDLE") or "bharatnova").lstrip("@")
BRAND = os.getenv("BRAND_NAME") or "bharatNova"
BRAND_MARK = (os.getenv("BRAND_MARK") or "bN")[:3]
VOICE_F = os.getenv("VOICE_FEMALE") or "mr-IN-AarohiNeural"
VOICE_M = os.getenv("VOICE_MALE") or "mr-IN-ManoharNeural"
VOICE_RATE = os.getenv("VOICE_RATE") or "+0%"
W, H, FPS = 720, 1280, 30          # reel
PW, PH = 1080, 1350                # post / carousel (4:5)
IST = timezone(timedelta(hours=5, minutes=30))

# ------------------------------------------------------------------ theme
GREEN_D = (10, 56, 36)
GREEN = (22, 128, 61)
LEAF = (86, 178, 92)
GOLD = (247, 181, 33)
CREAM = (255, 249, 232)
WHITE = (255, 255, 255)
DARK = (8, 32, 22)
RED = (214, 69, 65)


def A(c, a=1.0):
    return (c[0], c[1], c[2], max(0, min(255, int(255 * a))))


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def back(x):
    """overshoot ease: pops slightly past 1.0 then settles (zoom-punch feel)."""
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def dn(n):
    return str(n).translate(str.maketrans("0123456789", "०१२३४५६७८९"))


# ------------------------------------------------------------------ fonts (Mukta, Devanagari, shipped in fonts/)
_FD = {"black": ["Mukta-ExtraBold.ttf"], "bold": ["Mukta-Bold.ttf"], "med": ["Mukta-Medium.ttf"]}
_SYS = ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


@lru_cache(maxsize=None)
def font(kind, size):
    for n in _FD[kind]:
        p = BASE / "fonts" / n
        if p.exists():
            return ImageFont.truetype(str(p), size)
    for p in _SYS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ------------------------------------------------------------------ text helpers
def tokens(text):
    out, hl = [], False
    for part in re.split(r"(\*\*)", str(text)):
        if part == "**":
            hl = not hl
            continue
        out.extend((w, hl) for w in part.split())
    return out


def layout(d, toks, f, max_w):
    lines, cur = [[]], 0.0
    sp = d.textlength(" ", font=f)
    for w, hl in toks:
        wl = d.textlength(w, font=f)
        if lines[-1] and cur + sp + wl > max_w:
            lines.append([])
            cur = 0.0
        cur += (sp if lines[-1] else 0) + wl
        lines[-1].append((w, hl, wl))
    return lines, sp


def draw_rich(d, cx, y, text, kind, size, max_w, col, hl_col=GOLD, max_lines=3, lh=1.25, align="center", shadow=True):
    """Text with **highlighted** words. Shrinks to fit max_lines. Returns y below the block."""
    toks = tokens(text)
    while True:
        f = font(kind, size)
        lines, sp = layout(d, toks, f, max_w)
        if len(lines) <= max_lines or size <= 22:
            break
        size -= 3
    for line in lines:
        total = sum(w for _, _, w in line) + sp * (len(line) - 1)
        x = cx - total / 2 if align == "center" else cx
        for w, hl, wl in line:
            if shadow:
                d.text((x + 2, y + 3), w, font=f, fill=(0, 0, 0, min(150, col[3] if len(col) > 3 else 255)))
            d.text((x, y), w, font=f, fill=(hl_col if hl else col))
            x += wl + sp
        y += size * lh
    return y


def text_block(d, x, y, text, kind, size, max_w, col, max_lines=2, lh=1.25):
    toks = tokens(text)
    while True:
        f = font(kind, size)
        lines, sp = layout(d, toks, f, max_w)
        if len(lines) <= max_lines or size <= 20:
            break
        size -= 2
    for line in lines:
        d.text((x, y), " ".join(w for w, _, _ in line), font=f, fill=col)
        y += size * lh
    return y


def text_c(d, cx, y, s, kind, size, fill):
    f = font(kind, size)
    d.text((cx - d.textlength(s, font=f) / 2, y), s, font=f, fill=fill)


def panel(img, box, r, fill, outline=None, width=0):
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(img.width, x1), min(img.height, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    ov = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), r, fill=fill, outline=outline, width=width)
    img.alpha_composite(ov, (x0, y0))


# ------------------------------------------------------------------ icons (drawn, no emoji fonts needed)
def leaf(d, bx, by, tx, ty, bulge, col):
    dx, dy = tx - bx, ty - by
    ln = math.hypot(dx, dy) or 1
    nx, ny = -dy / ln, dx / ln
    pts = []
    for i in range(13):
        t = i / 12
        o = math.sin(math.pi * t) * bulge
        pts.append((bx + dx * t + nx * o, by + dy * t + ny * o))
    for i in range(12, -1, -1):
        t = i / 12
        o = -math.sin(math.pi * t) * bulge
        pts.append((bx + dx * t + nx * o, by + dy * t + ny * o))
    d.polygon(pts, fill=col)


def icon(d, kind, cx, cy, r, col=WHITE, col2=GOLD):
    a = col[3] if len(col) > 3 else 255
    if kind == "drop":
        d.ellipse((cx - r * .62, cy - r * .12, cx + r * .62, cy + r * 1.12), fill=col)
        d.polygon([(cx, cy - r * 1.05), (cx - r * .58, cy + r * .25), (cx + r * .58, cy + r * .25)], fill=col)
    elif kind == "sun":
        d.ellipse((cx - r * .5, cy - r * .5, cx + r * .5, cy + r * .5), fill=col2[:3] + (a,))
        for k in range(8):
            ang = k * math.pi / 4
            d.line((cx + math.cos(ang) * r * .72, cy + math.sin(ang) * r * .72, cx + math.cos(ang) * r * 1.05, cy + math.sin(ang) * r * 1.05),
                   fill=col2[:3] + (a,), width=max(3, int(r * .1)))
    elif kind == "wheat":
        d.line((cx, cy + r, cx, cy - r * .9), fill=col, width=max(3, int(r * .08)))
        for k in range(4):
            yy = cy - r * .8 + k * r * .38
            leaf(d, cx, yy + r * .2, cx - r * .5, yy - r * .25, r * .12, col2[:3] + (a,))
            leaf(d, cx, yy + r * .2, cx + r * .5, yy - r * .25, r * .12, col2[:3] + (a,))
        leaf(d, cx, cy - r * .7, cx, cy - r * 1.2, r * .12, col2[:3] + (a,))
    else:  # sprout
        d.line((cx, cy + r, cx, cy - r * .1), fill=col, width=max(4, int(r * .1)))
        leaf(d, cx, cy + r * .1, cx - r * .95, cy - r * .55, r * .32, col)
        leaf(d, cx, cy - r * .05, cx + r * .95, cy - r * .75, r * .32, col2[:3] + (a,))


def check(d, cx, cy, r, col):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD[:3] + (col[3],))
    d.line((cx - r * .45, cy, cx - r * .1, cy + r * .4, cx + r * .5, cy - r * .35), fill=A(GREEN_D, col[3] / 255), width=max(3, int(r * .28)), joint="curve")


# ------------------------------------------------------------------ backgrounds (your photos, or generated graphics)
def list_photos():
    ph = ASSETS / "photos"
    if not ph.exists():
        return []
    return [p for p in ph.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]


def pick_photo(tag, rnd, used):
    allp = list_photos()
    if not allp:
        return None
    cand = [p for p in allp if tag and tag.lower() in str(p.relative_to(ASSETS / "photos")).lower()] or allp
    fresh = [p for p in cand if p not in used] or cand
    p = rnd.choice(fresh)
    used.add(p)
    return p


def cover_crop(im, w, h):
    return ImageOps.fit(im.convert("RGB"), (w, h), method=Image.LANCZOS, centering=(0.5, 0.5))


def procedural(w, h, seed):
    rnd = random.Random(seed)
    pal = [((255, 226, 140), (250, 150, 60), (18, 92, 52), (38, 140, 70), (10, 60, 38)),       # sunrise
           ((196, 236, 214), (90, 190, 140), (14, 84, 56), (30, 130, 78), (8, 52, 36)),        # fresh
           ((255, 200, 120), (190, 110, 60), (20, 80, 50), (34, 120, 66), (10, 48, 32))][seed % 3]  # dusk
    sky = ImageOps.colorize(Image.linear_gradient("L").resize((w, h)), pal[0], pal[1]).convert("RGBA")
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    sx, sy, sr = int(w * rnd.uniform(.3, .7)), int(h * .26), int(w * .17)
    gd.ellipse((sx - sr * 2, sy - sr * 2, sx + sr * 2, sy + sr * 2), fill=(255, 240, 170, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(sr * .8))
    sky.alpha_composite(glow)
    ImageDraw.Draw(sky).ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(255, 247, 210, 255))
    d = ImageDraw.Draw(sky)
    for li, (col, base, amp) in enumerate([(pal[2], .50, .035), (pal[3], .58, .04), (pal[4], .66, .05)]):
        ph1, ph2 = rnd.uniform(0, 6), rnd.uniform(0, 6)
        pts = [(x, h * base + math.sin(x / w * 5 + ph1) * h * amp + math.sin(x / w * 11 + ph2) * h * amp * .4) for x in range(0, w + 20, 20)]
        d.polygon(pts + [(w, h), (0, h)], fill=col)
    vx, vy = w * rnd.uniform(.4, .6), h * .68                                  # crop rows toward a vanishing point
    for k in range(-9, 10):
        d.line((vx + k * 6, vy, w / 2 + k * w * .16, h), fill=pal[3] if k % 2 else (46, 150, 78), width=max(4, int(w * .012)))
    for k in range(6):
        x = w * (.08 + k * .17) + rnd.uniform(-20, 20)
        icon(d, "wheat", x, h * .90, h * .075, col=(226, 190, 70, 255), col2=(240, 205, 90, 255))
    return sky.convert("RGB")


_BG = {}


def get_bg(tag, w, h, seed, used):
    key = (tag, w, h, seed)
    if key in _BG:
        return _BG[key]
    p = pick_photo(tag, random.Random(seed), used)
    im = cover_crop(Image.open(p), w, h) if p else procedural(w, h, seed)
    _BG[key] = im
    return im


def kb_frame(bg, w, h, z, px=0.5, py=0.5):
    """Ken Burns: bg is 1.3x the output; z from 1.0 (whole image) to ~1.3 (zoomed in)."""
    bw, bh = bg.size
    cw, ch = bw / z, bh / z
    x0 = (bw - cw) * px
    y0 = (bh - ch) * py
    return bg.resize((w, h), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)).convert("RGBA")


@lru_cache(maxsize=4)
def shade(w, h, strong=1.0):
    ov = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(ov)
    for y in range(h):
        t = y / h
        a = 150 * (1 - t / .3) + 40 if t < .3 else (40 + (t - .3) / .7 * 170 if t > .55 else 40)
        d.line((0, y, w, y), fill=(6, 30, 20, int(min(235, a * strong))))
    return ov


# ------------------------------------------------------------------ reel visuals
def r_(t, i, step=0.35, dur=0.45, start=0.3):
    return ease((t - start - i * step) / dur)


def v_hook(img, d, v, t, S):
    cx, cy = W / 2, 560
    for k in range(3):                                           # expanding rings
        ph = ((t * .7 + k / 3) % 1.0)
        rr = 90 + ph * 190
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=A(GOLD, (1 - ph) * .55), width=4)
    s = 1 + .06 * math.sin(t * 3.2)
    a = back(t / .6)
    R = 120 * s * max(.2, a)
    d.ellipse((cx - R * 1.25, cy - R * 1.25, cx + R * 1.25, cy + R * 1.25), fill=A(GREEN_D, .78), outline=A(GOLD, .9), width=5)
    icon(d, v.get("icon", "sprout"), cx, cy - R * .02, R * .72, col=A(WHITE), col2=GOLD)
    if v.get("text"):
        al = ease((t - .5) / .5)
        panel(img, (50, 770, W - 50, 770 + 120), 26, A(DARK, .55 * al))
        text_block(d, 80, 782, v["text"], "bold", 34, W - 160, A(CREAM, al), max_lines=2)


def v_points(img, d, v, t, S):
    items = [str(x) for x in (v.get("items") or [])][:4]
    y = 380
    for i, it in enumerate(items):
        a = r_(t, i)
        if a <= 0:
            continue
        off = int((1 - a) * 90)
        panel(img, (46 + off, y, W - 46 + off, y + 112), 28, A(DARK, .62 * a), A(GOLD, .8 * a), 2)
        check(d, 100 + off, y + 56, 24, A(WHITE, a))
        text_block(d, 148 + off, y + 20, it, "bold", 36, W - 230, A(CREAM, a), max_lines=2)
        y += 128


def v_stat(img, d, v, t, S):
    val = str(v.get("value", "")).strip()
    unit = str(v.get("unit", ""))
    try:
        num = float(val)
        shown = f"{int(round(num * ease(t / 1.4)))}"
    except ValueError:
        shown = val
    cx, cy = W / 2, 560
    pulse = 1 + .03 * math.sin(t * 4)
    R = max(2, 215 * pulse * ease(t / .5))
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=A(GREEN_D, .72), outline=A(GOLD, .9), width=6)
    f = font("black", 190)
    full = shown + unit
    w = d.textlength(full, font=f)
    if w > 215 * 1.7:
        f = font("black", max(20, int(190 * 215 * 1.7 / w)))
        w = d.textlength(full, font=f)
    d.text((cx - w / 2 + 3, cy - 118 + 4), full, font=f, fill=(0, 0, 0, 120))
    d.text((cx - w / 2, cy - 118), full, font=f, fill=A(GOLD))
    al = ease((t - .6) / .5)
    if v.get("label"):
        panel(img, (50, 820, W - 50, 920), 26, A(DARK, .6 * al))
        draw_rich(d, W / 2, 832, v["label"], "bold", 34, W - 140, A(CREAM, al), max_lines=2, shadow=False)


def v_compare(img, d, v, t, S):
    cw = (W - 3 * 36) / 2
    for side, x0, col in (("left", 36, RED), ("right", 36 * 2 + cw, LEAF)):
        i = 0 if side == "left" else 1
        a = r_(t, i, step=.5)
        if a <= 0:
            continue
        data = v.get(side) or {}
        y0 = 370 + int((1 - a) * 60)
        panel(img, (x0, y0, x0 + cw, y0 + 500), 30, A(DARK, .66 * a), A(col, .95 * a), 4)
        panel(img, (x0 + 14, y0 + 14, x0 + cw - 14, y0 + 84), 20, A(col, .9 * a))
        text_c(d, x0 + cw / 2, y0 + 20, str(data.get("title", ""))[:22], "black", 32, A(WHITE, a))
        yy = y0 + 104
        for p in (data.get("points") or [])[:3]:
            yy = text_block(d, x0 + 22, yy, "• " + str(p), "bold", 28, cw - 44, A(CREAM, a), max_lines=2) + 12
        if data.get("metric"):
            text_c(d, x0 + cw / 2, y0 + 405, str(data["metric"])[:16], "black", 44, A(GOLD, a))
    b = ease((t - .8) / .4)
    if b > 0:
        d.ellipse((W / 2 - 32 * b, 600 - 32 * b, W / 2 + 32 * b, 600 + 32 * b), fill=A(GOLD), outline=A(GREEN_D), width=3)
        text_c(d, W / 2, 576, "VS", "black", 28, A(GREEN_D, b))


def v_steps(img, d, v, t, S):
    items = [str(x) for x in (v.get("items") or [])][:5]
    n = max(1, len(items))
    active = min(n - 1, int(max(0, t - .3) / max(.8, (S["dur"] - .6) / n)))
    y, step = 380, 98
    for i in range(n - 1):
        yy = y + i * step + 36
        d.line((100, yy + 10, 100, yy + step - 10), fill=A(GOLD, .7 if i < active else .25), width=5)
    for i, it in enumerate(items):
        a = r_(t, i, step=.28)
        if a <= 0:
            continue
        yy = y + i * step
        on = i <= active
        panel(img, (150, yy, W - 46, yy + 84), 24, A(DARK, (.7 if i == active else .5) * a), A(GOLD, .95 * a) if i == active else None, 3)
        d.ellipse((66, yy + 10, 134, yy + 78), fill=A(GOLD if on else GREEN, a))
        text_c(d, 100, yy + 6, dn(i + 1), "black", 44, A(GREEN_D if on else CREAM, a))
        text_block(d, 168, yy + 12, it, "bold", 30, W - 240, A(CREAM, a), max_lines=2, lh=1.15)


_PIMG = {}


def short_name(n):
    """"Soil Mate Pro (सॉईल मेट प्रो)" -> "Soil Mate Pro" for the on-screen title."""
    return str(n).split(" (")[0].strip()[:28]


def product_tile(v, w, h):
    key = (v.get("image"), v.get("name"), w, h)
    if key in _PIMG:
        return _PIMG[key]
    tile = Image.new("RGBA", (w, h), (255, 252, 240, 255))
    p = BASE / str(v.get("image") or "")
    if v.get("image") and p.is_file():
        src = Image.open(p).convert("RGB")
        bgf = ImageOps.fit(src, (w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(18)).convert("RGBA")   # soft backdrop from the photo itself
        bgf.alpha_composite(Image.new("RGBA", (w, h), (255, 255, 255, 70)))
        fg = ImageOps.contain(src, (int(w * .95), int(h * .97)), Image.LANCZOS).convert("RGBA")
        bgf.alpha_composite(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
        tile = bgf
    else:                                                          # placeholder until a real product photo is added
        g = ImageOps.colorize(Image.linear_gradient("L").resize((w, h)), (236, 247, 226), (190, 228, 180)).convert("RGBA")
        tile = g
        dd = ImageDraw.Draw(tile)
        icon(dd, "sprout", w / 2, h * .42, h * .24, col=A(GREEN), col2=GOLD)
        text_c(dd, w / 2, h * .70, str(v.get("name", ""))[:20], "black", 34, A(GREEN_D))
    _PIMG[key] = tile
    return tile


def v_product(img, d, v, t, S):
    cw, ch = W - 120, 290
    a = back(t / .6)
    z = 1 + .12 * min(1, t / max(1, S["dur"]))
    tile = product_tile(v, cw, ch)
    cx0, cy0 = (cw - cw / z) / 2, (ch - ch / z) / 2
    zi = tile.resize((cw, ch), Image.BILINEAR, box=(cx0, cy0, cx0 + cw / z, cy0 + ch / z))
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), 34, fill=int(255 * min(1, a)))
    sc = .85 + .15 * min(1, a)
    sw, sh = int(cw * sc), int(ch * sc)
    img.paste(zi.resize((sw, sh)), (int(W / 2 - sw / 2), int(370 + (ch - sh) / 2)), mask.resize((sw, sh)))
    d.rounded_rectangle((W / 2 - sw / 2, 370 + (ch - sh) / 2, W / 2 + sw / 2, 370 + (ch + sh) / 2), 34, outline=A(GOLD, .95), width=5)
    badge = ease((t - .5) / .4)
    panel(img, (70, 384, 70 + 170, 384 + 46), 23, A(GREEN, .95 * badge))
    text_c(d, 155, 386, BRAND, "black", 28, A(WHITE, badge))
    al = ease((t - .5) / .5)
    text_c(d, W / 2, 672, short_name(v.get("name", "")), "black", 46, A(GOLD, al))
    yy = 740
    for i, b in enumerate((v.get("benefits") or [])[:3]):
        a2 = r_(t, i, start=.8)
        if a2 <= 0:
            continue
        check(d, 92, yy + 24, 17, A(WHITE, a2))
        text_block(d, 126 + int((1 - a2) * 50), yy + 4, str(b), "bold", 30, W - 190, A(CREAM, a2), max_lines=1)
        yy += 54


def v_outro(img, d, v, t, S):
    cx = W / 2
    s = 1 + .05 * math.sin(t * 5)
    a = back(t / .6)
    bw, bh = 400 * s * a, 96 * s * a
    d.rounded_rectangle((cx - bw / 2, 400 - bh / 2, cx + bw / 2, 400 + bh / 2), 48, fill=A(GOLD), outline=A(WHITE), width=4)
    if a > .6:
        text_c(d, cx, 400 - 38, "फॉलो करा", "black", 54, A(GREEN_D))
    al = ease((t - .4) / .5)
    text_c(d, cx, 478, "@" + HANDLE, "black", 40, A(CREAM, al))
    if v.get("ask"):
        panel(img, (46, 560, W - 46, 700), 30, A(DARK, .62 * al), A(GOLD, .8 * al), 3)
        text_block(d, 76, 578, v["ask"], "bold", 34, W - 152, A(CREAM, al), max_lines=3)
    for i, (lab, ic) in enumerate((("सेव्ह करा", "sprout"), ("शेअर करा", "sun"), ("कमेंट करा", "drop"))):
        a3 = r_(t, i, start=.9, step=.25)
        if a3 <= 0:
            continue
        x = 130 + i * 230
        d.ellipse((x - 54, 770 - 54, x + 54, 770 + 54), fill=A(GREEN_D, .75 * a3), outline=A(GOLD, a3), width=3)
        icon(d, ic, x, 770, 30, col=A(WHITE, a3), col2=GOLD)
        text_c(d, x, 836, lab, "bold", 26, A(CREAM, a3))


VIS = {"hook": v_hook, "points": v_points, "stat": v_stat, "compare": v_compare, "steps": v_steps, "product": v_product, "outro": v_outro}


# ------------------------------------------------------------------ reel frame
def top_bar(img, d, S, gt, total):
    d.rectangle((0, 0, W * gt / max(total, 1), 7), fill=A(GOLD))
    panel(img, (28, 38, 28 + 62, 38 + 62), 18, A(GOLD))
    text_c(d, 59, 40, BRAND_MARK, "black", 38, A(GREEN_D))
    d.text((106, 44), BRAND, font=font("black", 34), fill=A(WHITE))
    d.text((106, 78), "@" + HANDLE, font=font("med", 22), fill=A(CREAM, .85))
    if S.get("tag"):
        f = font("bold", 24)
        tw_ = d.textlength(S["tag"], font=f)
        panel(img, (W - 40 - tw_ - 28, 46, W - 40, 92), 23, A(GREEN, .92))
        d.text((W - 40 - tw_ - 14, 50), S["tag"], font=f, fill=A(WHITE))


def caption_layout(scene, f, max_w, dd):
    words = str(scene["say"]).split()
    lines, sp = layout(dd, [(w, False) for w in words], f, max_w)
    out, k = [], 0
    for ln in lines:
        out.append((k, ln))
        k += len(ln)
    return out, sp


def draw_caption(img, d, lay, t, voice_len, y0):
    f = font("bold", 38)
    n = sum(len(ln) for _, ln in lay[0])
    cur = min(n - 1, int(max(0.0, t - .15) / max(.5, voice_len) * n))
    nl = len(lay[0])
    panel(img, (30, y0 - 14, W - 30, y0 + nl * 52 + 14), 26, (6, 30, 20, 150))
    for li, (k0, ln) in enumerate(lay[0]):
        total = sum(w for _, _, w in ln) + lay[1] * (len(ln) - 1)
        x, y = W / 2 - total / 2, y0 + li * 52
        for j, (w, _, wl) in enumerate(ln):
            idx = k0 + j
            col = A(GOLD) if idx == cur else (A(WHITE) if idx < cur else A(CREAM, .6))
            d.text((x, y), w, font=f, fill=col)
            x += wl + lay[1]


class ReelPainter:
    def __init__(self, spec, durs, vlens):
        self.spec, self.durs, self.vlens = spec, durs, vlens
        self.total = sum(durs)
        self.used = set()
        n = len(spec["scenes"])
        self.bgs = []
        for i, sc in enumerate(spec["scenes"]):
            self.bgs.append(get_bg(sc.get("bg", ""), int(W * 1.3), int(H * 1.3), 100 + i, self.used))
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        self.caps = [caption_layout(sc, font("bold", 38), W - 110, tmp) for sc in spec["scenes"]]
        self.heads = [self._head(sc.get("head", "")) for sc in spec["scenes"]]
        self.shade = shade(W, H)

    def _head(self, text):
        lay = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        draw_rich(d, W / 2, 4, text, "black", 62, W - 90, A(WHITE), max_lines=3, lh=1.18)
        return lay

    def frame(self, i, t, gt):
        sc = self.spec["scenes"][i]
        dur = self.durs[i]
        p = t / dur
        z = 1.0 + .22 * p if i % 2 == 0 else 1.22 - .22 * p                # alternate zoom in / zoom out
        punch = .10 * (1 - ease(t / .45))                                  # quick zoom-punch at every cut
        img = kb_frame(self.bgs[i], W, H, z + punch, .5 + (.12 if i % 3 == 0 else -.12 if i % 3 == 1 else 0) * (p - .5), .5)
        img.alpha_composite(self.shade)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        top_bar(img, d, {"tag": self.spec.get("tag", "")}, gt, self.total)
        img.alpha_composite(lay)
        # headline: zoom-in pop
        hl = self.heads[i]
        s = 1.0 + .45 * (1 - back(t / .5)) if t < .5 else 1.0
        al = ease(t / .25)
        if s != 1.0 or al < 1:
            hh = hl.resize((int(W * s), int(330 * s)), Image.BILINEAR)
            if al < 1:
                hh.putalpha(hh.getchannel("A").point(lambda v_: int(v_ * al)))
        else:
            hh = hl
        hl_lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hl_lay.paste(hh, (int((W - hh.width) / 2), int(140 - (hh.height - 330) / 2)))
        img.alpha_composite(hl_lay)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        fn = VIS.get(sc["visual"]["type"], v_hook)
        fn(img, d, sc["visual"], t, {"dur": dur})
        draw_caption(img, d, self.caps[i], t, self.vlens[i], 912)
        img.alpha_composite(lay)
        return img


# ------------------------------------------------------------------ voice
def _run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def audio_len(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


async def _tts(text, voice, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=VOICE_RATE).save(str(out))


def tts_text(say):
    """Clean the sentence for the voice: pauses stay, symbols that sound robotic go."""
    t = re.sub(r"\s*(?:[—–|]| - )\s*", ", ", str(say))
    t = re.sub(r"\s+", " ", t).strip()
    return t if re.search(r"[.!?।…]$", t) else t + "."


def speak_edge(text, gender, out):
    prim = VOICE_M if gender == "M" else VOICE_F
    backup = ["hi-IN-MadhurNeural"] if gender == "M" else ["hi-IN-SwaraNeural"]
    for voice in [prim, prim] + backup:
        try:
            asyncio.run(_tts(text, voice, out))
            if Path(out).exists() and Path(out).stat().st_size > 800:
                return voice
        except Exception as ex:
            print(f"edge voice {voice} failed: {str(ex)[:150]}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError("edge-tts: no voice could be generated")


# ---- Gemini TTS (free tier): much more natural than edge-tts. Natural-language style prompt controls the acting.
TTS = (os.getenv("TTS_PROVIDER") or "gemini").lower()               # gemini | edge
GTTS_VOICE = {"F": os.getenv("GEMINI_TTS_VOICE_F") or "Sulafat", "M": os.getenv("GEMINI_TTS_VOICE_M") or "Charon"}
GTTS_SAFE = {"F": "Kore", "M": "Charon"}                            # used if the chosen voice name is rejected
GTTS_MODELS = [m for m in dict.fromkeys([os.getenv("GEMINI_TTS_MODEL") or "", "gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]) if m]
GTTS_LEGACY = ["gemini-2.5-flash-preview-tts"]
GTTS_STYLE = {
    "F": os.getenv("GEMINI_TTS_STYLE_F") or "warm, friendly and natural Marathi as spoken in Maharashtra, like a caring village agriculture tai talking to farmers; "
                                           "relaxed medium pace, small natural pauses at commas, gentle smile in the voice, never robotic or newsreader-like",
    "M": os.getenv("GEMINI_TTS_STYLE_M") or "calm, friendly and natural Marathi as spoken in Maharashtra, like an experienced farmer dada talking to fellow farmers; "
                                           "relaxed medium pace, natural pauses at commas, sincere and conversational, never robotic or newsreader-like",
}
G_API = "https://generativelanguage.googleapis.com/v1beta"


def _find_audio(o):
    if isinstance(o, dict):
        if o.get("type") == "audio" and isinstance(o.get("data"), str):
            return o["data"]
        for k in ("inlineData", "inline_data"):
            if isinstance(o.get(k), dict) and isinstance(o[k].get("data"), str):
                return o[k]["data"]
        for v in o.values():
            r = _find_audio(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in reversed(o):
            r = _find_audio(v)
            if r:
                return r
    return None


def _save_audio(b64, out):
    import base64
    import wave
    raw = base64.b64decode(b64)
    if raw[:4] == b"RIFF":
        Path(out).write_bytes(raw)
    else:                                                            # raw 24 kHz 16-bit mono PCM
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(raw)


def gemini_tts(text, gender, out):
    import requests
    hdr = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
    voice, style = GTTS_VOICE[gender], GTTS_STYLE[gender]
    errs, deadline = [], time.time() + 240
    for model in GTTS_MODELS + GTTS_LEGACY:
        legacy = "2.5" in model
        for attempt in range(4):
            if time.time() > deadline:
                raise RuntimeError("Gemini TTS: out of time | " + " | ".join(errs[-3:]))
            try:
                if legacy:
                    r = requests.post(f"{G_API}/models/{model}:generateContent", headers=hdr, timeout=180, json={
                        "contents": [{"parts": [{"text": f"Say in a {style} tone: {text}"}]}],
                        "generationConfig": {"responseModalities": ["AUDIO"],
                                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}})
                else:
                    r = requests.post(f"{G_API}/interactions", headers=hdr, timeout=120, json={
                        "model": model,
                        "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                                   "annotations": [{"type": "speech_metadata", "style": style}]}]}],
                        "response_format": {"type": "audio"},
                        "generation_config": {"speech_config": [{"voice": voice}]}})
            except requests.RequestException as ex:
                errs.append(f"{model}: network {str(ex)[:80]}")
                time.sleep(5)
                continue
            if r.ok:
                try:
                    data = _find_audio(r.json())
                except Exception:
                    data = None
                if data:
                    _save_audio(data, out)
                    return f"gemini-tts:{voice}"
                errs.append(f"{model}: reply had no audio")
                break
            errs.append(f"{model}: {r.status_code} {r.text[:110]}")
            print(f"Gemini TTS {model}: {r.status_code}", file=sys.stderr)
            if r.status_code == 400 and re.search(r"voice", r.text, re.I) and voice != GTTS_SAFE[gender]:
                voice = GTTS_SAFE[gender]                              # this voice name does not exist for the key: use a safe one
                continue
            if r.status_code == 429:
                if re.search(r"PerDay|per day|daily|limit: 0", r.text, re.I):
                    break
                time.sleep(min(60, 20 * (attempt + 1)))
                continue
            if r.status_code in (500, 502, 503, 504):
                time.sleep(8)
                continue
            break
    raise RuntimeError("Gemini TTS failed: " + " | ".join(errs[-4:]))


_TRIM = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.04,areverse,"
         "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.04,areverse")


# ---- Sarvam (Bulbul): built for Indian languages, natural Marathi (mr-IN). Needs SARVAM_API_KEY (paid after the signup credits).
SARVAM_F = os.getenv("SARVAM_FEMALE") or "ritu"
SARVAM_M = os.getenv("SARVAM_MALE") or "ashutosh"
SARVAM_MODEL = os.getenv("SARVAM_MODEL") or "bulbul:v3"
SARVAM_PACE = float(os.getenv("SARVAM_PACE") or 0.95)


def sarvam_tts(text, gender, out):
    import base64
    import requests
    speaker = SARVAM_M if gender == "M" else SARVAM_F
    body = {"text": text, "target_language_code": "mr-IN", "speaker": speaker, "model": SARVAM_MODEL,
            "pace": SARVAM_PACE, "speech_sample_rate": 24000}
    extras = {"temperature": 0.6, "enable_preprocessing": True}          # not every model version accepts these: dropped on a 400/422
    use_extras, err = True, ""
    for attempt in range(4):
        r = requests.post("https://api.sarvam.ai/text-to-speech",
                          headers={"api-subscription-key": os.environ["SARVAM_API_KEY"], "Content-Type": "application/json"},
                          json={**body, **(extras if use_extras else {})}, timeout=90)
        if r.ok:
            Path(out).write_bytes(base64.b64decode(r.json()["audios"][0]))
            return f"sarvam:{speaker}"
        err = f"{r.status_code}: {r.text[:250]}"
        print(f"Sarvam {err}", file=sys.stderr)
        if r.status_code in (400, 422) and use_extras:
            use_extras = False
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(6 * (attempt + 1))
            continue
        break
    raise RuntimeError("Sarvam " + err)


def eleven_tts(text, gender, out):
    import requests
    vid = os.environ["ELEVEN_VOICE_M"] if gender == "M" else os.environ["ELEVEN_VOICE_F"]
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                      headers={"xi-api-key": os.environ["ELEVEN_API_KEY"]},
                      json={"text": text, "model_id": os.getenv("ELEVEN_MODEL") or "eleven_v3"}, timeout=90)
    r.raise_for_status()
    Path(out).write_bytes(r.content)
    return "elevenlabs"


PROVIDERS = {"sarvam": (sarvam_tts, "wav", 0.5), "elevenlabs": (eleven_tts, "mp3", 0.5), "gemini": (gemini_tts, "wav", 3.0), "edge": (speak_edge, "mp3", 0)}


def provider_chain():
    first = (os.getenv("VOICE_PROVIDER") or os.getenv("TTS_PROVIDER") or ("sarvam" if os.getenv("SARVAM_API_KEY") else "gemini")).lower()
    first = first if first in PROVIDERS else "gemini"
    return [first] + [p for p in ("gemini", "edge") if p != first]


def _scene_raws(spec, tmp):
    """One raw clip per scene from ONE provider (Sarvam > Gemini > edge by default). If a provider fails on any scene,
    the whole video is redone with the next one, so the two voices never change halfway through a Reel."""
    for prov in provider_chain():
        fn, ext, gap = PROVIDERS[prov]
        raws, names = [], set()
        try:
            for i, sc in enumerate(spec["scenes"]):
                raw = tmp / f"r{i:02d}.{ext}"
                names.add(fn(tts_text(sc["say"]), sc.get("voice", "F"), raw))
                raws.append(raw)
                time.sleep(gap)
            return raws, ", ".join(sorted(names))
        except Exception as ex:
            print(f"VOICE PROVIDER {prov} FAILED -> next provider. Reason: {str(ex)[:300]}", file=sys.stderr)
    raise RuntimeError("no voice could be generated")


def build_audio(spec, tmp, fake=False):
    durs, vlens, wavs = [], [], []
    raws, vname = (None, "silent") if fake else _scene_raws(spec, tmp)
    for i, sc in enumerate(spec["scenes"]):
        t1, wav = tmp / f"t{i:02d}.wav", tmp / f"s{i:02d}.wav"
        if fake:
            secs = max(2.6, len(sc["say"].split()) / 2.3)
            _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{secs:.2f}", str(t1)])
        else:
            _run(["ffmpeg", "-v", "error", "-y", "-i", str(raws[i]), "-af", _TRIM, "-ar", "44100", "-ac", "1", str(t1)])
        vl = audio_len(t1)
        dur = max(2.6, vl + .15 + .40)
        _run(["ffmpeg", "-v", "error", "-y", "-i", str(t1), "-af", "adelay=150|150,apad", "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "1", str(wav)])
        durs.append(dur)
        vlens.append(vl)
        wavs.append(wav)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{w}'\n" for w in wavs))
    full = tmp / "voice.wav"
    _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", str(full)])
    music = sorted((ASSETS / "music").glob("*.mp3")) if (ASSETS / "music").exists() else []
    if music and not fake:                                             # optional royalty-free music you add yourself
        mixed = tmp / "mixed.wav"
        _run(["ffmpeg", "-v", "error", "-y", "-i", str(full), "-stream_loop", "-1", "-i", str(random.choice(music)), "-filter_complex",
              "[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:normalize=0", "-ar", "44100", str(mixed)])
        full = mixed
    return durs, vlens, full, vname


def render_reel(spec, durs, vlens, audio, out_path, preview_dir=None):
    painter = ReelPainter(spec, durs, vlens)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac", "-b:a", "160k",
           "-shortest", "-movflags", "+faststart", str(out_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    gt = 0.0
    for i in range(len(spec["scenes"])):
        nf = int(round(durs[i] * FPS))
        for f in range(nf):
            t = f / FPS
            im = painter.frame(i, t + (.45 if i == 0 else 0), gt + t)
            p.stdin.write(im.convert("RGB").tobytes())
            if preview_dir and f in (int(1.6 * FPS), nf - 2):
                im.convert("RGB").save(Path(preview_dir) / f"scene{i:02d}_{'a' if f != nf - 2 else 'b'}.png")
        gt += durs[i]
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed while rendering the reel")
    return painter.total


# ------------------------------------------------------------------ static slides (posts + carousels, 1080x1350)
def slide_frame(slide, i, n, spec, used):
    typ = slide.get("type", "point")
    bg = get_bg(slide.get("bg", ""), int(PW * 1.3), int(PH * 1.3), 500 + i, used)
    zooms = [1.0, 1.14, 1.07, 1.2, 1.03, 1.16, 1.1, 1.0, 1.12, 1.05]            # every slide is a different zoom level
    pans = [(.5, .5), (.3, .4), (.7, .5), (.5, .3), (.35, .6), (.65, .35), (.5, .6), (.4, .4), (.6, .6), (.5, .5)]
    img = kb_frame(bg, PW, PH, zooms[i % 10], *pans[i % 10])
    img.alpha_composite(shade(PW, PH, 1.1))
    lay = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    # header
    panel(img, (50, 52, 50 + 84, 52 + 84), 24, A(GOLD))
    text_c(d, 92, 54, BRAND_MARK, "black", 52, A(GREEN_D))
    d.text((152, 56), BRAND, font=font("black", 46), fill=A(WHITE))
    d.text((152, 108), "@" + HANDLE, font=font("med", 30), fill=A(CREAM, .85))
    if spec.get("tag"):
        f = font("bold", 32)
        w_ = d.textlength(spec["tag"], font=f)
        panel(img, (PW - 50 - w_ - 40, 66, PW - 50, 124), 29, A(GREEN, .95))
        d.text((PW - 50 - w_ - 20, 70), spec["tag"], font=f, fill=A(WHITE))
    head, body = slide.get("head", ""), slide.get("body", "")
    if typ == "cover":
        icon(d, slide.get("icon", "sprout"), PW / 2, 360, 120, col=A(WHITE), col2=GOLD)
        y = draw_rich(d, PW / 2, 520, head, "black", 118, PW - 130, A(WHITE), max_lines=4, lh=1.17)
        if body:
            panel(img, (80, y + 20, PW - 80, y + 20 + 130), 34, A(DARK, .55))
            text_block(d, 120, y + 38, body, "bold", 42, PW - 240, A(CREAM), max_lines=2)
        panel(img, (PW / 2 - 210, PH - 190, PW / 2 + 210, PH - 190 + 92), 46, A(GOLD))
        text_c(d, PW / 2 - 30, PH - 190 + 14, "स्वाइप करा", "black", 52, A(GREEN_D))
        ax = PW / 2 + 150
        d.polygon([(ax, PH - 190 + 26), (ax + 34, PH - 190 + 46), (ax, PH - 190 + 66)], fill=A(GREEN_D))
    elif typ == "stat":
        cx, cy = PW / 2, 560
        d.ellipse((cx - 300, cy - 300, cx + 300, cy + 300), fill=A(GREEN_D, .75), outline=A(GOLD), width=8)
        full = str(slide.get("value", "")) + str(slide.get("unit", ""))
        f = font("black", 280)
        w_ = d.textlength(full, font=f)
        if w_ > 520:
            f = font("black", int(280 * 520 / w_))
            w_ = d.textlength(full, font=f)
        d.text((cx - w_ / 2, cy - 170), full, font=f, fill=A(GOLD))
        draw_rich(d, PW / 2, 920, head, "black", 70, PW - 140, A(WHITE), max_lines=2)
        if body:
            panel(img, (70, 1090, PW - 70, 1240), 34, A(DARK, .6))
            text_block(d, 110, 1108, body, "bold", 40, PW - 220, A(CREAM), max_lines=2)
    elif typ == "product":
        cw, ch = PW - 160, 520
        tile = product_tile({"image": slide.get("image"), "name": slide.get("name", "")}, cw, ch)
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), 50, fill=255)
        img.paste(tile, (80, 190), mask)
        d.rounded_rectangle((80, 190, 80 + cw, 190 + ch), 50, outline=A(GOLD), width=7)
        draw_rich(d, PW / 2, 745, short_name(slide.get("name") or head), "black", 84, PW - 140, A(GOLD), max_lines=2, lh=1.1)
        yy = 905
        for b in (slide.get("benefits") or [])[:3]:
            check(d, 130, yy + 34, 26, A(WHITE))
            text_block(d, 176, yy + 6, str(b), "bold", 44, PW - 260, A(CREAM), max_lines=1)
            yy += 84
        if body:
            text_block(d, 80, yy + 12, body, "bold", 36, PW - 160, A(CREAM, .9), max_lines=2)
    elif typ == "cta":
        icon(d, "sprout", PW / 2, 330, 110, col=A(WHITE), col2=GOLD)
        y = draw_rich(d, PW / 2, 480, head or "आवडलं? **फॉलो** करा!", "black", 100, PW - 140, A(WHITE), max_lines=3, lh=1.17)
        panel(img, (PW / 2 - 300, y + 30, PW / 2 + 300, y + 140), 55, A(GOLD))
        text_c(d, PW / 2, y + 40, "@" + HANDLE, "black", 66, A(GREEN_D))
        yy = y + 190
        for lab in ("सेव्ह करा", "शेअर करा", "कमेंटमध्ये सांगा"):
            panel(img, (160, yy, PW - 160, yy + 84), 42, A(DARK, .6), A(GOLD, .8), 3)
            text_c(d, PW / 2, yy + 8, lab, "bold", 46, A(CREAM))
            yy += 104
        if body:
            text_block(d, 100, yy + 10, body, "bold", 38, PW - 200, A(CREAM, .9), max_lines=2)
    else:                                                                   # point / tip
        num = slide.get("number")
        y = 230
        if num:
            d.ellipse((60, y, 60 + 150, y + 150), fill=A(GOLD), outline=A(WHITE), width=5)
            text_c(d, 135, y + 10, dn(num), "black", 100, A(GREEN_D))
            icon(d, slide.get("icon", "sprout"), PW - 150, y + 80, 70, col=A(WHITE), col2=GOLD)
            y += 190
        else:
            icon(d, slide.get("icon", "sprout"), PW / 2, y + 70, 90, col=A(WHITE), col2=GOLD)
            y += 190
        y = draw_rich(d, 80, y, head, "black", 92, PW - 160, A(WHITE), max_lines=3, lh=1.15, align="left")
        if body:
            by = y + 24
            ghost = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
            end = text_block(ghost, 100, by + 28, body, "bold", 46, PW - 200, A(CREAM), max_lines=5, lh=1.28)
            panel(img, (60, by, PW - 60, min(PH - 150, end + 28)), 40, A(DARK, .62), A(GOLD, .7), 3)
            text_block(d, 100, by + 28, body, "bold", 46, PW - 200, A(CREAM), max_lines=5, lh=1.28)
    # footer dots
    if n > 1:
        for k in range(n):
            x = PW / 2 + (k - (n - 1) / 2) * 34
            d.ellipse((x - 9, PH - 60, x + 9, PH - 42), fill=A(GOLD if k == i else WHITE, 1 if k == i else .4))
    img.alpha_composite(lay)
    return img.convert("RGB")


# ------------------------------------------------------------------ AI: planning + scripts
STATE_FILE = BASE / "state.json"
CATEGORIES = ["माती आरोग्य आणि सेंद्रिय खत", "पाणी व्यवस्थापन आणि ठिबक सिंचन", "कीड-रोग व्यवस्थापन (एकात्मिक पद्धत)", "हंगामी पीक नियोजन",
              "फळबाग आणि भाजीपाला", "बियाणे निवड आणि प्रक्रिया", "शेतीपूरक व्यवसाय (दुग्ध, कुक्कुट, मधमाशी)", "काढणीनंतरचे व्यवस्थापन आणि साठवण",
              "आधुनिक शेती तंत्रज्ञान (ड्रोन, सेन्सर, मोबाइल अॅप)", "खर्च कमी करण्याच्या युक्त्या"]
SEEDS = ["ठिबक सिंचनाचे फायदे", "जीवामृत घरच्या घरी कसे बनवायचे", "माती परीक्षण का करावे", "आच्छादन (मल्चिंग) चे फायदे", "पिकांची फेरपालट",
         "गांडूळ खत निर्मिती", "बीजप्रक्रियेचे महत्त्व", "पिवळे चिकट सापळे (यलो स्टिकी ट्रॅप)", "हिरवळीचे खत (ताग, धैंचा)", "उन्हाळ्यात फळबागेचे पाणी नियोजन"]


def season_hint(now=None):
    m = (now or datetime.now(IST)).month
    if 6 <= m <= 9:
        return "खरीप हंगाम (सोयाबीन, कापूस, तूर, भात, मका, बाजरी) - पावसाळा, तण आणि रोग नियंत्रण"
    if m in (10, 11):
        return "रब्बी पेरणीचा काळ (गहू, हरभरा, ज्वारी, कांदा, करडई) - जमीन तयारी, बियाणे प्रक्रिया"
    if m in (12, 1, 2):
        return "रब्बी वाढीचा काळ (गहू, हरभरा, कांदा, ऊस, द्राक्ष) - थंडी, सिंचन नियोजन"
    return "उन्हाळी हंगाम (भुईमूग, भाजीपाला, फळबाग) - उष्णता आणि पाणी टंचाई व्यवस्थापन"


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"used": []}


def save_state(s):
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def _toks(t):
    return set(re.findall(r"[^\s,.;:!?()\-–—/\"'|]+", t.lower()))


def too_similar(topic, used):
    a = _toks(topic)
    for u in used:
        b = _toks(u)
        if a and b and len(a & b) / len(a | b) >= .6:
            return True
    return False


def clean_json(raw):
    return json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip())


def plan_topic(state):
    import core
    used = [u["topic"] for u in state["used"]]
    cat = CATEGORIES[len(used) % len(CATEGORIES)]
    prompt = f"""तुम्ही महाराष्ट्रातील शेतकऱ्यांसाठी Instagram पेज 'bharatNova' चे कंटेंट प्लॅनर आहात.
विभाग: {cat}
सध्याचा हंगाम: {season_hint()}
आधी वापरलेले विषय (पुन्हा नको): {used[-60:]}
या विभागातील 8 नवीन, व्यावहारिक, अचूक आणि महाराष्ट्राच्या शेतकऱ्याला उपयोगी विषय सुचवा. सरकारी योजनांचे आकडे, बाजारभाव किंवा औषधांचे डोस असलेले विषय नको.
फक्त JSON: {{"topics":["...", "..."]}}"""
    try:
        for t in clean_json(core.call_gemini(prompt)).get("topics", []):
            if isinstance(t, str) and t.strip() and not too_similar(t, used):
                return t.strip(), cat
    except Exception as ex:
        print(f"planner failed: {str(ex)[:150]}", file=sys.stderr)
    for t in SEEDS:
        if not too_similar(t, used):
            return t, cat
    return random.choice(SEEDS) + f" ({len(used)})", cat


def load_products():
    p = BASE / "products.json"
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [x for x in items if x.get("enabled")]


def pick_product(state, pid=""):
    items = load_products()
    if not items:
        raise RuntimeError("products.json madhe ekahi 'enabled': true product nahi. Aadhi product details bhara.")
    if pid:
        for x in items:
            if x["id"] == pid:
                return x
    counts = {x["id"]: 0 for x in items}
    for u in state["used"]:
        if u.get("product") in counts:
            counts[u["product"]] += 1
    return min(items, key=lambda x: counts[x["id"]])


RULES = """भाषा आणि नियम (आवाज नैसर्गिक वाटण्यासाठी हे सर्वात महत्त्वाचे):
- "say" = आवाजातील वाक्य; संपूर्ण वाक्य शुद्ध देवनागरीत. लहान वाक्ये (8-14 शब्द). बोलल्यासारखी सोपी, रोजची मराठी (पुस्तकी नको). 'तुम्ही' वापरा.
- इंग्रजी शब्द देवनागरीत लिहा, लॅटिन अक्षरे नकोत: drip = ड्रिप, NPK = एनपीके, pH = पीएच, spray = स्प्रे, mulching = मल्चिंग, bharatNova = भारतनोव्हा. उत्पादनाचे नाव दिलेल्या कंसातील मराठी रूपात लिहा.
- अंक आणि चिन्हे नकोत: संख्या शब्दांत लिहा (पन्नास टक्के, पंधरा ते वीस दिवस, दोन ते तीन मिली). '%', '50', '2-3' असे काहीही नको.
- नैसर्गिक थांब्यासाठी वाक्यात स्वल्पविराम (,) वापरा आणि गरज असेल तेव्हा '...' वापरा. डॅश (-, —) किंवा कंसातील वाक्ये नकोत.
- "voice" = "F" (स्त्री निवेदिका) किंवा "M" (पुरुष). संवाद शैली: M शेतकरी प्रश्न विचारतो / समस्या सांगतो, F उत्तर देते; आलटून पालटून.
- "head" = स्क्रीनवरील छोटे शीर्षक (जास्तीत जास्त 8 शब्द, मराठी); 1-2 मुख्य शब्द **दोन तारकांमध्ये** लिहा. (हे फक्त स्क्रीनसाठी; येथे अंक/इंग्रजी चालेल.)
- "bg" = पार्श्वभूमीचा विषय एका इंग्रजी शब्दात: crops, soil, water, farm, fruits, vegetables, tractor, sunrise, product.
- सर्व माहिती अचूक हवी. आकडे फक्त सर्वमान्य आणि "साधारणपणे / पर्यंत" सह; माहीत नसतील तर देऊ नका. खोटी आकडेवारी, सरकारी योजनांचे आकडे, बाजारभाव कधीही नको.
- कीटकनाशक/रासायनिक खतांचे डोस किंवा नावे देऊ नका; गरज असल्यास "जवळच्या कृषी विज्ञान केंद्र / कृषी अधिकाऱ्याचा सल्ला घ्या" असे सांगा.
- कोणताही राजकीय, धार्मिक किंवा जातीय उल्लेख नको."""

VIS_DOC = """VISUAL प्रकार (visual.type):
 {"type":"hook","icon":"sprout|drop|sun|wheat","text":"<पहिल्या सीनचा प्रश्न/समस्या, 18 शब्दांत>"}     (फक्त सीन 1 आणि गरज असल्यास मध्ये)
 {"type":"points","items":["..","..",".."]}                                              (2-4 मुद्दे, प्रत्येक 8 शब्दांपर्यंत)
 {"type":"stat","value":"50","unit":"%","label":"पर्यंत पाण्याची बचत (पिकानुसार बदलते)"}     (फक्त खात्रीशीर, सर्वमान्य आकडा; value फक्त अंक)
 {"type":"compare","left":{"title":"पारंपरिक","points":["..","..",".."],"metric":"जास्त खर्च"},"right":{"title":"सुधारित","points":["..",".."],"metric":"कमी खर्च"}}
 {"type":"steps","items":["..","..","..",".."]}                                               (3-5 टप्पे, प्रत्येक 7 शब्दांपर्यंत)
 {"type":"outro","ask":"<कमेंटसाठी छोटा प्रश्न, मराठीत>"}                                        (फक्त शेवटचा सीन)"""

REEL_PROMPT = """तुम्ही महाराष्ट्रातील शेतकऱ्यांना सोप्या मराठीत शिकवणारे अनुभवी कृषी तज्ज्ञ आहात आणि Instagram Reels चे स्क्रिप्ट लेखक आहात.
पेज: bharatNova. आजचा विषय: {topic}
सध्याचा हंगाम: {season}
रील 60-80 सेकंदांचा, उभा (vertical), आकर्षक ग्राफिक्ससह. 11-14 सीन; सर्व "say" मिळून 150-175 शब्दांपेक्षा जास्त नकोत.
रचना: सीन 1 = शेतकऱ्याच्या समस्येचा हुक (उदा. "तुमच्या पिकाला पाणी कमी पडतंय का?") -> समस्या -> मुख्य कल्पना -> टप्प्याटप्प्याने कसे करायचे -> फायदा/आकडा (असल्यास) -> सामान्य चूक -> एका ओळीत सार -> शेवटचा सीन outro (फॉलो / कमेंट).
हुक मध्येच "शेवटी एक चूक सांगतो जी बरेच जण करतात" असे वाक्य घाला आणि शेवटी उत्तर द्या.
{rules}

{vis}
प्रत्येक सीनमध्ये एकच ठोस गोष्ट शिकवा; विविध visual वापरा.
फक्त JSON:
{{"title":"<विषय, 5 शब्द>","tag":"<मराठी टॅग, जसे: शेती ज्ञान / पाणी / माती / फळबाग>",
 "scenes":[{{"say":"...","voice":"F","head":"...","bg":"crops","visual":{{...}}}}],
 "caption":"<मराठी Instagram कॅप्शन, 4-6 छोट्या ओळी, पहिली ओळ हुक प्रश्न, hashtag नको, 450 अक्षरांपर्यंत>",
 "comment_q":"<कमेंटसाठी एक प्रश्न, मराठीत>",
 "hashtags":["#...6-8 टॅग"]}}
HASHTAG नियम: कमी स्पर्धेचे, विषयाशी थेट संबंधित (उदा. #ठिबकसिंचन #जीवामृत #शेतकरीमित्र #marathifarmer #krushidnyan). #viral #reels #explore #fyp #trending सारखे मोठे टॅग नको.
हे विषय पुन्हा नको: {recent}
"""

AD_PROMPT = """तुम्ही 'bharatNova' या कृषी कंपनीसाठी प्रामाणिक, सोप्या मराठीतील Instagram Reel जाहिरात लिहिणारे कॉपीरायटर आहात.
उत्पादनाची माहिती (फक्त हीच वापरा, यात नसलेला कोणताही दावा, आकडा, किंमत, प्रमाणपत्र किंवा परिणाम लिहू नका):
{product}
सध्याचा हंगाम: {season}
रील 45-65 सेकंदांचा; 9-12 सीन; सर्व "say" मिळून 115-150 शब्द.
रचना: सीन 1 = शेतकऱ्याची समस्या (M आवाज) -> bharatNova चे उत्पादन ओळख (F) -> visual "product" वापरून नाव + 3 फायदे -> वापर कसा (फक्त दिलेल्या माहितीनुसार) -> कोणासाठी उपयुक्त -> शेवटचा सीन outro (CTA: उत्पादनातील cta वापरा).
जाहिरात नियम: "दुप्पट उत्पन्न", "100% हमी", "चमत्कारिक" असे अतिशयोक्त किंवा हमीचे दावे नाहीत; दुसऱ्या कंपन्यांची तुलना/निंदा नाही; "पिकानुसार व जमिनीनुसार परिणाम वेगळे असू शकतात" असे एक वाक्य घाला; वापराआधी लेबलवरील सूचना वाचा असे सांगा.
{rules}

{vis}
 {{"type":"product","name":"<उत्पादनाचे नाव>","image":"<product.image हेच>","benefits":["..","..",".."]}}   (benefits फक्त दिलेल्या माहितीतून, प्रत्येक 6 शब्दांपर्यंत; 1 किंवा 2 सीनमध्ये)
फक्त JSON:
{{"title":"<उत्पादन नाव>","tag":"bharatNova","scenes":[{{"say":"...","voice":"M","head":"...","bg":"product","visual":{{...}}}}],
 "caption":"<मराठी कॅप्शन 4-6 ओळी, hashtag नको, 450 अक्षरांपर्यंत>","comment_q":"<एक प्रश्न, मराठीत>","hashtags":["#bharatnova","#...6-8 टॅग"]}}
"""

SLIDES_PROMPT = """तुम्ही महाराष्ट्रातील शेतकऱ्यांसाठी Instagram {fmt} चे कंटेंट लेखक आहात. पेज: bharatNova. विषय: {topic}. सध्याचा हंगाम: {season}
{count}
{rules_short}
प्रत्येक स्लाईड:
 {{"type":"cover|point|stat|cta","head":"मोठे शीर्षक (8 शब्दांपर्यंत, 1-2 शब्द **तारकांत**)","body":"1-2 छोटी वाक्ये (25 शब्दांपर्यंत)","number":<point साठी क्रमांक>,"icon":"sprout|drop|sun|wheat","bg":"crops|soil|water|farm|fruits|vegetables|sunrise","value":"stat साठी अंक","unit":"%"}}
पहिली स्लाईड cover (आकर्षक हुक), शेवटची cta ("आवडलं? **फॉलो** करा").
फक्त JSON: {{"title":"...","tag":"<मराठी टॅग>","slides":[...],"caption":"<मराठी कॅप्शन 4-6 ओळी, hashtag नको>","comment_q":"<एक प्रश्न>","hashtags":["#..6-8"]}}
HASHTAG: कमी स्पर्धेचे, विषयाशी संबंधित; #viral #reels #explore #fyp सारखे मोठे नको. हे विषय पुन्हा नको: {recent}
"""

PSLIDES_PROMPT = """तुम्ही 'bharatNova' कृषी कंपनीसाठी प्रामाणिक मराठी Instagram {fmt} कॉपी लिहिता.
उत्पादनाची माहिती (फक्त हीच वापरा; नसलेले दावे, आकडे, किंमत, प्रमाणपत्र लिहू नका):
{product}
{count}
नियम: अतिशयोक्ती/हमी नाही ("दुप्पट उत्पन्न", "100% हमी" वगैरे), इतरांची निंदा नाही, एका स्लाईडवर "लेबलवरील सूचना वाचा; परिणाम पिकानुसार बदलू शकतात" असे लिहा. बाकी भाषा सोपी मराठी देवनागरी; 'तुम्ही' वापरा. राजकीय/धार्मिक उल्लेख नको.
स्लाईड प्रकार: cover, point (फायदा/वापर), product {{"type":"product","name":"...","image":"<product.image>","benefits":["..","..",".."],"body":"..."}}, cta (उत्पादनाचा cta वापरा).
प्रत्येक स्लाईडमध्ये "type","head","body","bg":"product","icon":"sprout|drop|sun|wheat"; point साठी "number".
फक्त JSON: {{"title":"...","tag":"bharatNova","slides":[...],"caption":"<मराठी कॅप्शन 4-6 ओळी, hashtag नको>","comment_q":"<एक प्रश्न>","hashtags":["#bharatnova","#.. 6-8"]}}
"""


def _dev(s):
    return bool(re.search(r"[\u0900-\u097F]", str(s)))


def validate_reel(spec, ad=False):
    sc = spec.get("scenes") or []
    if not 4 <= len(sc) <= 18:
        raise ValueError(f"bad scene count {len(sc)}")
    words = 0
    for i, s in enumerate(sc):
        s["say"] = str(s.get("say", "")).strip()
        if not s["say"] or not _dev(s["say"]):
            raise ValueError(f"scene {i}: voice-over must be Marathi (Devanagari)")
        if re.search(r"[A-Za-z0-9०-९%]", s["say"]):
            raise ValueError(f"scene {i}: voice-over must have no Latin letters, digits or % (write English words and numbers in Devanagari words)")
        if len(s["say"].split()) > 20:
            raise ValueError(f"scene {i}: sentence too long for a natural voice ({len(s['say'].split())} words)")
        words += len(s["say"].split())
        s["voice"] = "M" if str(s.get("voice", "F")).upper().startswith("M") else "F"
        s["head"] = str(s.get("head") or "")
        v = s.get("visual") or {}
        if v.get("type") not in VIS:
            v = {"type": "hook", "icon": "sprout"}
        s["visual"] = v
    if words > 215:
        raise ValueError(f"too long: {words} words")
    sc[0]["visual"] = sc[0]["visual"] if sc[0]["visual"]["type"] == "hook" else {"type": "hook", "icon": "sprout", "text": sc[0]["head"].replace("**", "")}
    sc[-1]["visual"] = sc[-1]["visual"] if sc[-1]["visual"]["type"] == "outro" else {"type": "outro", "ask": spec.get("comment_q", "")}
    if ad and not any(s["visual"]["type"] == "product" for s in sc):
        raise ValueError("ad reel has no product scene")
    return spec


def validate_slides(spec, lo, hi):
    sl = spec.get("slides") or []
    if not lo <= len(sl) <= hi:
        raise ValueError(f"bad slide count {len(sl)}")
    for s in sl:
        if not _dev(s.get("head", "")):
            raise ValueError("slide text must be Marathi")
        s["head"], s["body"] = str(s.get("head", "")), str(s.get("body", ""))
    sl[0]["type"] = "cover" if sl[0].get("type") != "product" else "product"
    return spec


def gen(prompt, validator, tries=3):
    import core
    last = None
    for k in range(tries):
        try:
            return validator(clean_json(core.call_gemini(prompt)))
        except Exception as ex:
            last = ex
            print(f"script attempt {k + 1} rejected: {str(ex)[:160]}", file=sys.stderr)
    raise RuntimeError(f"could not get a valid script: {last}")


def product_json(p):
    keep = {k: p.get(k) for k in ("id", "name", "category", "tagline", "benefits", "usage", "suitable_for", "pack_sizes", "cta", "image", "note") if p.get(k)}
    return json.dumps(keep, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ samples (no AI, no voice) to check the look
SAMPLE_REEL = {
    "title": "ठिबक सिंचन", "tag": "पाणी व्यवस्थापन",
    "scenes": [
        {"say": "शेतकरी मित्रांनो, उन्हाळ्यात विहिरीचं पाणी कमी पडतं का?", "voice": "M", "head": "पाणी **कमी** पडतंय?", "bg": "water",
         "visual": {"type": "hook", "icon": "drop", "text": "कमी पाण्यात जास्त क्षेत्र भिजवायचंय?"}},
        {"say": "मग ठिबक सिंचन तुमच्यासाठी आहे. यात पाणी थेट झाडाच्या मुळाजवळ थेंब थेंब दिलं जातं.", "voice": "F", "head": "**ठिबक** सिंचन म्हणजे काय?", "bg": "crops",
         "visual": {"type": "steps", "items": ["टाकी किंवा विहीर", "फिल्टर", "मुख्य पाईपलाईन", "ड्रिपर: थेट मुळाशी"]}},
        {"say": "पाटाच्या पाण्यात बरंच पाणी वाया जातं आणि तणही वाढतं.", "voice": "M", "head": "पाट विरुद्ध **ठिबक**", "bg": "farm",
         "visual": {"type": "compare", "left": {"title": "पाटपाणी", "points": ["पाणी वाया", "तण जास्त", "मजुरी जास्त"], "metric": "जास्त पाणी"},
                    "right": {"title": "ठिबक", "points": ["थेट मुळाशी", "तण कमी", "मजुरी कमी"], "metric": "कमी पाणी"}}},
        {"say": "साधारणपणे पिकानुसार पन्नास टक्क्यांपर्यंत पाण्याची बचत होऊ शकते.", "voice": "F", "head": "पाण्याची **बचत**", "bg": "sunrise",
         "visual": {"type": "stat", "value": "50", "unit": "%", "label": "पर्यंत पाण्याची बचत (पिकानुसार बदलते)"}},
        {"say": "पण एक चूक टाळा: फिल्टर साफ केला नाही तर ड्रिपर चोक होतात.", "voice": "M", "head": "ही **चूक** टाळा", "bg": "soil",
         "visual": {"type": "points", "items": ["फिल्टर नियमित साफ करा", "ड्रिपर चोक झालेत का तपासा", "पिकानुसार पाण्याचा वेळ ठरवा"]}},
        {"say": "रोज अशी शेतीची माहिती हवी असेल, तर भारतनोव्हाला फॉलो करा.", "voice": "F", "head": "रोज **शेती** ज्ञान", "bg": "sunrise",
         "visual": {"type": "outro", "ask": "तुम्ही कोणत्या पिकाला ठिबक वापरता?"}},
    ],
    "caption": "उन्हाळ्यात पाणी कमी पडतंय का? 💧\nठिबक सिंचनात पाणी थेट मुळाशी दिलं जातं, त्यामुळे पाण्याची बचत होऊ शकते.\nफिल्टर नियमित साफ करा आणि ड्रिपर तपासत रहा.",
    "comment_q": "तुम्ही कोणत्या पिकाला ठिबक वापरता?", "hashtags": ["#ठिबकसिंचन", "#शेतकरीमित्र", "#marathifarmer", "#krushidnyan"],
}
SAMPLE_AD = {
    "title": "bharatNova नमुना उत्पादन", "tag": "bharatNova",
    "scenes": [
        {"say": "माती कडक झालीय आणि पिकाची वाढ मंदावलीय, असं होतंय का?", "voice": "M", "head": "माती **कडक** झालीय?", "bg": "soil",
         "visual": {"type": "hook", "icon": "sprout", "text": "मातीचं आरोग्य म्हणजे पिकाचं आरोग्य"}},
        {"say": "यासाठी भारतनोव्हा घेऊन आलंय, हे नमुना उत्पादन.", "voice": "F", "head": "bharatNova **नमुना** उत्पादन", "bg": "product",
         "visual": {"type": "product", "name": "नमुना उत्पादन", "image": "assets/products/germee.png", "benefits": ["पहिला फायदा", "दुसरा फायदा", "तिसरा फायदा"]}},
        {"say": "वापरण्याआधी लेबलवरील सूचना नक्की वाचा; परिणाम पिकानुसार बदलू शकतात.", "voice": "M", "head": "वापर **सूचना**", "bg": "farm",
         "visual": {"type": "points", "items": ["लेबल वाचा", "शिफारस केलेलं प्रमाण वापरा", "शंका असल्यास कृषी अधिकाऱ्यांना विचारा"]}},
        {"say": "अधिक माहितीसाठी प्रोफाइलवरील लिंक पहा, आणि भारतनोव्हाला फॉलो करा.", "voice": "F", "head": "आजच **फॉलो** करा", "bg": "sunrise",
         "visual": {"type": "outro", "ask": "तुम्हाला कोणत्या उत्पादनाची माहिती हवी?"}},
    ],
    "caption": "(नमुना) bharatNova चं नवीन उत्पादन.\nवापरण्याआधी लेबलवरील सूचना वाचा.", "comment_q": "तुम्हाला कोणत्या उत्पादनाची माहिती हवी?", "hashtags": ["#bharatnova"],
}
SAMPLE_SLIDES = {
    "title": "जीवामृत", "tag": "सेंद्रिय शेती",
    "slides": [
        {"type": "cover", "head": "घरच्या घरी **जीवामृत** कसं बनवायचं?", "body": "खर्च कमी, मातीसाठी चांगलं", "icon": "sprout", "bg": "soil"},
        {"type": "point", "number": 1, "head": "साहित्य **गोळा** करा", "body": "देशी गायीचं शेण व गोमूत्र, गूळ, बेसन, शेतातली माती आणि पाणी.", "icon": "wheat", "bg": "farm"},
        {"type": "point", "number": 2, "head": "सगळं **मिसळा**", "body": "पिंपात पाणी घेऊन साहित्य नीट मिसळा आणि सावलीत ठेवा.", "icon": "drop", "bg": "water"},
        {"type": "stat", "head": "**आंबवा**", "value": "48", "unit": " तास", "body": "रोज सकाळ-संध्याकाळ काठीने ढवळा.", "bg": "sunrise"},
        {"type": "point", "number": 3, "head": "पिकाला **द्या**", "body": "पाण्याबरोबर किंवा फवारणीसाठी शिफारस केलेल्या प्रमाणात वापरा.", "icon": "sprout", "bg": "crops"},
        {"type": "cta", "head": "आवडलं? **फॉलो** करा!", "body": "तुमचा अनुभव कमेंटमध्ये लिहा.", "bg": "sunrise"},
    ],
    "caption": "जीवामृत घरच्या घरी कसं बनवायचं? 🌱\nसाहित्य गोळा करा, मिसळा, आंबवा आणि वापरा. सोपं आणि कमी खर्चाचं!",
    "comment_q": "तुम्ही जीवामृत वापरता का?", "hashtags": ["#जीवामृत", "#सेंद्रियशेती", "#shetkarimitra"],
}

# ------------------------------------------------------------------ caption + publishing
BIG_TAGS = {"#viral", "#reels", "#reel", "#trending", "#explore", "#fyp", "#instagood", "#love", "#instagram", "#india", "#farming", "#agriculture"}


def build_caption(spec, kind):
    cap = str(spec.get("caption", "")).strip()
    parts = [cap]
    cq = str(spec.get("comment_q") or "").strip()
    if cq:
        parts.append(f"{cq} कमेंटमध्ये सांगा 👇")
    if kind.startswith("reel_ad") or kind.startswith("product"):
        parts.append("अधिक माहितीसाठी प्रोफाइलवरील लिंक पहा. वापरण्याआधी लेबलवरील सूचना वाचा.")
    parts.append("सेव्ह करा 🔖 शेअर करा 🤝 आणि रोजच्या शेती ज्ञानासाठी फॉलो करा 🌾")
    parts.append(f"@{HANDLE}")
    tags = [t.lower() for t in (spec.get("hashtags") or []) if isinstance(t, str) and t.startswith("#")]
    tags = [t for t in tags if t not in BIG_TAGS]
    allt = list(dict.fromkeys(tags[:8] + ["#शेतकरी", "#शेतीज्ञान", "#marathifarmer", "#bharatnova"]))[:12]
    parts.append(" ".join(allt))
    return "\n\n".join(p for p in parts if p)[:2200]


def to_jpg(img, path):
    img.convert("RGB").save(path, "JPEG", quality=92, optimize=True)


def resolve_kind(kind):
    now = datetime.now(IST)
    if kind == "noon":
        return "carousel" if now.timetuple().tm_yday % 2 == 0 else "post"
    if kind == "evening":
        return {0: "reel_ad", 2: "reel_ad", 4: "reel_ad", 1: "product_carousel", 3: "product_carousel", 5: "product_post", 6: "product_post"}[now.weekday()]
    return kind


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="reel_agri", choices=["reel_agri", "reel_ad", "carousel", "post", "product_carousel", "product_post", "noon", "evening"])
    ap.add_argument("--topic", default="")
    ap.add_argument("--product", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--previews", action="store_true")
    a = ap.parse_args()
    print(VERSION, file=sys.stderr)
    OUT_DIR.mkdir(exist_ok=True)
    kind = resolve_kind(a.kind)
    stamp = time.strftime("%Y%m%d_%H%M")
    state = load_state()
    ad = kind in ("reel_ad", "product_carousel", "product_post")
    product, topic, cat = None, a.topic, "Manual"
    if not a.sample:
        import core
        recent = [u["topic"] for u in state["used"][-40:]] + [c.split("\n")[0][:80] for c in core.ig_recent_captions(25)]
        if ad:
            product = pick_product(state, a.product)
            topic = product["name"]
        elif not topic:
            topic, cat = plan_topic(state)
        print(f"KIND: {kind} | TOPIC: {topic} | {cat}", file=sys.stderr)
    season = season_hint()
    pj = product_json(product) if product else ""
    media_id, cap = None, ""
    if kind in ("reel_agri", "reel_ad"):
        if a.sample:
            spec = json.loads(json.dumps(SAMPLE_AD if kind == "reel_ad" else SAMPLE_REEL))
            spec = validate_reel(spec, ad=(kind == "reel_ad"))
        elif kind == "reel_ad":
            spec = gen(AD_PROMPT.format(product=pj, season=season, rules=RULES, vis=VIS_DOC), lambda s: validate_reel(s, ad=True))
        else:
            spec = gen(REEL_PROMPT.format(topic=topic, season=season, rules=RULES, vis=VIS_DOC, recent=recent[-30:]), validate_reel)
        if product:                       # make sure the real product photo/name is on screen, whatever the AI wrote
            for s in spec["scenes"]:
                if s["visual"]["type"] == "product":
                    s["visual"]["image"] = product.get("image", "")
                    s["visual"]["name"] = product["name"]
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            durs, vlens, audio, voice = build_audio(spec, tmp, fake=a.sample)
            out = OUT_DIR / f"{stamp}_{kind}.mp4"
            prev = None
            if a.previews or a.sample:
                prev = OUT_DIR / "previews"
                prev.mkdir(exist_ok=True)
            secs = render_reel(spec, durs, vlens, audio, out, prev)
        cap = build_caption(spec, kind)
        print(f"video: {out} ({secs:.0f}s, voices: {voice})", file=sys.stderr)
        files = [out]
    else:
        count = 1 if kind in ("post", "product_post") else None
        fmt = "post (एकच इमेज)" if count == 1 else "कॅरोसेल (swipe)"
        cnt_txt = "फक्त 1 स्लाईड बनवा (type: point, number नको; शीर्षक + ठोस टीप)." if count == 1 else "7 स्लाईड बनवा."
        lo, hi = (1, 1) if count == 1 else (5, 9)
        if a.sample:
            spec = json.loads(json.dumps(SAMPLE_SLIDES))
            if count == 1:
                spec["slides"] = [dict(spec["slides"][1], number=None)]
        elif ad:
            spec = gen(PSLIDES_PROMPT.format(fmt=fmt, product=pj, count=cnt_txt), lambda s: validate_slides(s, lo, hi))
        else:
            rules_short = RULES.split("\n", 1)[1]
            spec = gen(SLIDES_PROMPT.format(fmt=fmt, topic=topic, season=season, count=cnt_txt, rules_short=rules_short, recent=recent[-30:]),
                       lambda s: validate_slides(s, lo, hi))
        if product:
            for s in spec["slides"]:
                if s.get("type") == "product":
                    s["image"], s["name"] = product.get("image", ""), product["name"]
        used, files = set(), []
        n = len(spec["slides"])
        for i, s in enumerate(spec["slides"]):
            p = OUT_DIR / f"{stamp}_{kind}_{i + 1:02d}.jpg"
            to_jpg(slide_frame(s, i, n, spec, used), p)
            files.append(p)
        cap = build_caption(spec, kind)
        print(f"images: {len(files)}", file=sys.stderr)
    (OUT_DIR / f"{stamp}_{kind}.txt").write_text(cap, encoding="utf-8")
    print(cap)
    if a.dry_run or a.sample:
        return
    import core
    try:
        if kind in ("reel_agri", "reel_ad"):
            media_id = core.publish(core.upload_video(str(files[0])), cap, reel=True)
        elif len(files) == 1:
            media_id = core.publish(core.upload_image(str(files[0])), cap, reel=False)
        else:
            media_id = core.publish_carousel([core.upload_image(str(f)) for f in files], cap)
    except Exception as ex:
        msg = str(ex)
        print(f"POST FAILED: {msg[:400]}", file=sys.stderr)
        if "190" in msg or "OAuth" in msg or "access token" in msg.lower():
            print("-> Instagram token valid nahi. IG_ACCESS_TOKEN (IGAA... ) ani IG_USER_ID (fakt digits) secrets tapasa.", file=sys.stderr)
        sys.exit(3)
    print(f"POSTED {kind}: {media_id}", file=sys.stderr)
    ok = core.first_comment(media_id, spec.get("comment_q", ""))          # every post gets exactly one comment from us
    if not ok:
        (OUT_DIR / "comment_failed.txt").write_text(str(media_id), encoding="utf-8")
        print("WARNING: post is live but the first comment was NOT added.", file=sys.stderr)
    state["used"].append({"topic": topic, "kind": kind, "cat": cat, "product": product and product["id"], "date": time.strftime("%Y-%m-%d"), "media": media_id})
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        sys.exit(1)
