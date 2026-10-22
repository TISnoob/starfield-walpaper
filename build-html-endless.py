#!/usr/bin/env python3
"""
build-html-endless.py - make starfield-endless.html: the starfield wallpaper that never repeats.

Run it:
    python3 build-html-endless.py               (on Windows:  py build-html-endless.py)

That writes starfield-endless.html next to where you run it. It is one small web page; open
it in a browser to see it, or hand it to a live-wallpaper app (see README.md). Nothing is
downloaded and nothing is installed: this script needs only Python 3.8 or newer.

What makes it "endless": the plain page (build-html.py) replays the same short loop everywhere
on the screen, and after a while your eye picks it up. This page also re-rolls patches of the
sky at random moments, so no spot of the screen keeps repeating.

Make it your own (all optional):
    python3 build-html-endless.py --palette ember  # star colours: default, ice, ember, aurora, mono
    python3 build-html-endless.py --density 1.5    # more stars (0.5 = half as many)
    python3 build-html-endless.py --speed 0.5      # slower drift (0 = the stars stand still)
    python3 build-html-endless.py --seed 42        # a different sky
    python3 build-html-endless.py --life 3         # change faster (default 5 seconds per patch)
    python3 build-html-endless.py --sky black      # no haze along the bottom of the screen
    python3 build-html-endless.py --out my-sky.html

The page itself takes settings, added to its address or file name, for example
    starfield-endless.html?life=3&scale=2
        life=5     average seconds before a patch is re-rolled (smaller = more change)
        fade=0.6   seconds a change-over takes (0 = instantly, the lightest on the computer)
        seed=12    a fixed starting arrangement (otherwise a new one every time it opens)
        scale=2    stars drawn 2 times bigger (for 4K screens)
"""
import argparse
import base64
import struct
import sys
import zlib

# =============================================================================================
#  The star generator. This part is the same in all four build-*.py scripts, so each script
#  works on its own. Every star is made by the code below - there are no image files.
# =============================================================================================
if sys.version_info < (3, 8):
    sys.exit("This script needs Python 3.8 or newer (you have %d.%d). Get it from https://www.python.org/downloads/"
             % sys.version_info[:2])

TILE_W, TILE_H = 540, 80      # the sky is built from a small animated "tile" of this size (pixels) ...
FPS = 20                      # ... played at this many frames per second
LEVELS = 40                   # brightness steps per star colour (6 colours x 40 steps = 240 palette entries)
SKY_START = 0.42              # the faint haze at the bottom of the screen starts this far down (0 = top)
DEFAULT_SKY = (2, 3, 6)       # ... and ends in this colour at the very bottom (red, green, blue 0-255)
LAYOUT_SEED = 7               # default arrangement of the patches (same default in the web pages)


# --------------------------------------------------------------------------------------------
#  Random numbers: "mulberry32". Tiny, fast, and gives the same numbers on every computer.
#  The web pages use the very same generator, so a seed means the same thing everywhere.
# --------------------------------------------------------------------------------------------
class Rng(object):
    def __init__(self, seed):
        self.a = int(seed) & 0xFFFFFFFF

    def random(self):                                   # a float from 0 up to (not including) 1
        self.a = (self.a + 0x6D2B79F5) & 0xFFFFFFFF
        a = self.a
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def uniform(self, lo, hi):
        return lo + (hi - lo) * self.random()

    def randint(self, lo, hi):                          # whole number, both ends included
        return lo + int(self.random() * (hi - lo + 1))

    def pick(self, weights):                            # index chosen with the given relative weights
        r = self.random() * sum(weights)
        for i, w in enumerate(weights):
            r -= w
            if r < 0:
                return i
        return len(weights) - 1


# --------------------------------------------------------------------------------------------
#  Colours. A palette has six "slots": main colour, second, third, accent, pale and white.
#  Each slot is a base colour (red, green, blue as 0-1 fractions, brightest channel = 1). Dim
#  stars are that colour darker; the brightest ones turn whiter (the 2nd number = how much).
# --------------------------------------------------------------------------------------------
PALETTES = {
    "default": dict(white=(0.97, 0.95, 1.00), slots=[
        ((0.04, 0.08, 1.00), 0.25), ((0.05, 0.50, 1.00), 0.25), ((0.26, 0.14, 1.00), 0.25),
        ((0.78, 0.32, 1.00), 0.30), ((0.45, 0.55, 1.00), 0.30), ((0.93, 0.93, 1.00), 0.00)]),
    "ice": dict(white=(0.92, 0.97, 1.00), slots=[
        ((0.05, 0.32, 1.00), 0.25), ((0.04, 0.58, 1.00), 0.25), ((0.02, 0.82, 1.00), 0.25),
        ((0.40, 0.62, 1.00), 0.30), ((0.62, 0.84, 1.00), 0.30), ((0.90, 0.96, 1.00), 0.00)]),
    "ember": dict(white=(1.00, 0.95, 0.82), slots=[
        ((1.00, 0.34, 0.04), 0.25), ((1.00, 0.58, 0.08), 0.25), ((1.00, 0.14, 0.10), 0.25),
        ((1.00, 0.84, 0.20), 0.30), ((1.00, 0.72, 0.46), 0.30), ((1.00, 0.94, 0.84), 0.00)]),
    "aurora": dict(white=(0.92, 1.00, 0.97), slots=[
        ((0.04, 0.90, 0.42), 0.25), ((0.02, 0.76, 0.72), 0.25), ((0.10, 0.50, 1.00), 0.25),
        ((0.62, 0.30, 1.00), 0.30), ((0.52, 0.95, 0.74), 0.30), ((0.90, 1.00, 0.96), 0.00)]),
    "mono": dict(white=(1.00, 1.00, 1.00), slots=[
        ((0.74, 0.80, 1.00), 0.30), ((0.90, 0.90, 1.00), 0.30), ((0.58, 0.64, 0.92), 0.30),
        ((1.00, 0.95, 0.90), 0.30), ((0.82, 0.88, 1.00), 0.30), ((1.00, 1.00, 1.00), 0.00)]),
}
MAIN, WHITE = 0, 5                                     # the first and the last of the six colour slots


def smoothstep(a, b, x):
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    s = (x - a) / (b - a)
    return s * s * (3.0 - 2.0 * s)


def build_palette(name):
    """Palette entry 0 = "no star" (transparent); then LEVELS brightness steps for each of the six colours."""
    spec = PALETTES[name]
    pal = [(0, 0, 0)]
    for base, whiten in spec["slots"]:
        for level in range(1, LEVELS + 1):
            b = level / LEVELS
            m = whiten * smoothstep(0.55, 1.0, b)
            pal.append(tuple(int(b * ((1 - m) * base[i] + m * spec["white"][i]) * 255 + 0.5) for i in range(3)))
    return pal


# --------------------------------------------------------------------------------------------
#  The stars. Five kinds, from faint dust to a few big glittering ones. For each kind:
#    rate    how many appear (per 10,000 tile pixels, per frame of the loop)
#    bright  peak brightness range (above 1 = the middle of the star is "burnt out" white-hot)
#    life    how many frames a star lasts (it fades in and out, so it twinkles)
#    speed   drift in pixels per frame (always down and to the right; bigger stars drift faster)
#    flicker random per-frame dimming, so dim dust sparkles
#    rays    (only the big ones) thin faint rays going up, down, left and right
#    shapes  which pixel pattern it has (see SHAPES), with weights
#    colours how likely each colour slot is (main, second, third, accent, pale, white)
#  The numbers were tuned until the whole sky feels like a dense, quietly twinkling starfield.
# --------------------------------------------------------------------------------------------
KINDS = {
    "dust":   dict(rate=21.1, bright=(0.040, 0.143), life=(4, 14), speed=(0.10, 0.50), flicker=0.50,
                   shapes=(("dot", .75), ("pair", .25)), colours=(.42, .16, .26, .13, .03, 0.0)),
    "speck":  dict(rate=5.88, bright=(0.169, 0.562), life=(5, 20), speed=(0.12, 0.55), flicker=0.35,
                   shapes=(("dot", .30), ("pair", .38), ("tri", .20), ("block", .12)), colours=(.40, .16, .24, .16, .04, 0.0)),
    "dot":    dict(rate=8.34, bright=(0.436, 1.237), life=(8, 26), speed=(0.15, 0.65), flicker=0.20,
                   shapes=(("dot", .10), ("pair", .30), ("tri", .25), ("block", .25), ("plus", .10)),
                   colours=(.34, .20, .14, .14, .14, .04)),
    "star":   dict(rate=0.656, bright=(0.644, 2.582), life=(12, 32), speed=(0.30, 0.90), flicker=0.0,
                   shapes=(("block", .30), ("plus", .10), ("blob", .60)), colours=(.22, .17, .08, .22, .14, .17)),
    "bright": dict(rate=0.030, bright=(1.0, 1.0), life=(26, 38), speed=(0.50, 0.90), flicker=0.0, rays=True,
                   shapes=(("glint", 1.0),), colours=(0.0, .10, 0.0, .15, .15, .60)),
}


def _shape_dot(r):
    return [(0, 0, 1.0)]


def _shape_pair(r):                                     # two pixels side by side
    dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[r.randint(0, 3)]
    return [(0, 0, 1.0), (dx, dy, r.uniform(0.55, 1.0))]


def _shape_tri(r):                                      # an L of three pixels, or a short line of three
    w = r.uniform(0.5, 0.9)
    if r.random() < 0.5:
        a = ((1, 0), (-1, 0))[r.randint(0, 1)]
        b = ((0, 1), (0, -1))[r.randint(0, 1)]
        return [(0, 0, 1.0), (a[0], a[1], w), (b[0], b[1], w)]
    if r.random() < 0.5:
        return [(-1, 0, w), (0, 0, 1.0), (1, 0, w)]
    return [(0, -1, w), (0, 0, 1.0), (0, 1, w)]


def _shape_block(r):                                    # a little 2 x 2 square
    return [(0, 0, 1.0), (1, 0, r.uniform(0.6, 1.0)), (0, 1, r.uniform(0.6, 1.0)), (1, 1, r.uniform(0.5, 0.95))]


def _shape_plus(r):
    w = r.uniform(0.40, 0.62)
    s = [(0, 0, 1.0), (1, 0, w), (-1, 0, w), (0, 1, w), (0, -1, w)]
    if r.random() < 0.5:
        s += [(dx, dy, w * 0.4) for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1))]
    return s


def _shape_blob(r):                                     # a soft round star, 3 x 3 with a faint ring
    s = [(0, 0, 1.0)]
    s += [(dx, dy, r.uniform(0.62, 0.80)) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    s += [(dx, dy, r.uniform(0.30, 0.50)) for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1))]
    s += [(dx, dy, 0.14) for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))]
    return s


def _shape_glint(r):                                    # the big ones: a bright 2 x 2 core with a halo
    s = [(0, 0, 1.0), (1, 0, 1.0), (0, 1, 1.0), (1, 1, 1.0)]
    for dx in range(-1, 3):
        for dy in range(-1, 3):
            if 0 <= dx <= 1 and 0 <= dy <= 1:
                continue
            edge = (dx in (-1, 2)) + (dy in (-1, 2))
            s.append((dx, dy, 0.55 if edge == 1 else 0.28))
    return s


SHAPES = {"dot": _shape_dot, "pair": _shape_pair, "tri": _shape_tri, "block": _shape_block,
          "plus": _shape_plus, "blob": _shape_blob, "glint": _shape_glint}


def envelope(u, peak_at):
    """0 -> 1 -> 0 over u = 0..1 with the top at u = peak_at. Plain arithmetic only, so every computer agrees."""
    s = u / peak_at if u <= peak_at else (1.0 - u) / (1.0 - peak_at)
    return s * s * (3.0 - 2.0 * s)


class Tile(object):
    """frames x (TILE_W x TILE_H) palette indices (0 = empty) plus the palette itself."""

    def __init__(self, frames, index, palette):
        self.frames, self.index, self.palette = frames, index, palette


def make_tile(seed=1, frames=60, density=1.0, speed=1.0, palette="default"):
    """Make the animated star tile. It loops seamlessly in time and wraps around on all four edges."""
    rng = Rng(seed)
    pal = build_palette(palette)
    npix = TILE_W * TILE_H
    index = [bytearray(npix) for _ in range(frames)]
    level = [bytearray(npix) for _ in range(frames)]
    stars = []
    for k in KINDS.values():
        count = int(k["rate"] * 1e-4 * npix * frames * density + 0.5)
        stars += [k] * count
    for k in stars:
        life = min(rng.randint(*k["life"]), frames - 1)
        start = rng.randint(0, frames - 1)               # the frame the star appears in
        x0, y0 = rng.uniform(0, TILE_W), rng.uniform(0, TILE_H)
        v = rng.uniform(*k["speed"]) * speed
        vx, vy = v * rng.uniform(0.5, 0.95), v * rng.uniform(0.5, 0.95)      # down and to the right
        peak = rng.uniform(*k["bright"])
        peak_at = rng.uniform(0.3, 0.6)
        slot = rng.pick(k["colours"])
        if slot == WHITE:
            peak = max(peak, 0.85)                       # white stars are always bright ones
        shape = SHAPES[k["shapes"][rng.pick([w for _, w in k["shapes"]])][0]](rng)
        rays = k.get("rays", False)
        if rays:
            arm, arm_w = rng.randint(8, 16), rng.uniform(0.16, 0.26)
        for age in range(life):
            f = (start + age) % frames
            b = peak * envelope((age + 0.5) / life, peak_at)
            if k["flicker"]:
                b *= 1.0 - k["flicker"] * rng.random()
            cx, cy = int(x0 + vx * age + 0.5), int(y0 + vy * age + 0.5)
            idx, lev = index[f], level[f]
            for dx, dy, w in shape:
                lv = int(b * w * LEVELS + 0.5)
                if lv < 1:
                    continue
                if lv > LEVELS:
                    lv = LEVELS
                o = ((cy + dy) % TILE_H) * TILE_W + (cx + dx) % TILE_W
                if lv > lev[o]:                          # where two stars overlap, the brighter one wins
                    lev[o] = lv
                    idx[o] = 1 + slot * LEVELS + (lv - 1)
            if rays:                                     # thin faint rays, up/down/left/right
                for j in range(2, 2 + arm):
                    lv = int(b * arm_w * (1.0 - (j - 2) / arm) * LEVELS + 0.5)
                    if lv < 1:
                        break
                    for dx, dy in ((j + 1, 0), (-j, 0), (0, j + 1), (0, -j)):
                        o = ((cy + dy) % TILE_H) * TILE_W + (cx + dx) % TILE_W
                        if lv > lev[o]:
                            lev[o] = lv
                            idx[o] = 1 + MAIN * LEVELS + (lv - 1)
    return Tile(frames, index, pal)


# --------------------------------------------------------------------------------------------
#  Small helpers shared by the scripts
# --------------------------------------------------------------------------------------------
def parse_sky(text):
    """'navy' (default), 'black' (none), 'purple', or a colour like '#101830' - the colour at the very bottom."""
    names = {"navy": DEFAULT_SKY, "black": (0, 0, 0), "none": (0, 0, 0), "purple": (6, 2, 9), "blue": (1, 4, 12)}
    t = text.strip().lower()
    if t in names:
        return names[t]
    if t.startswith("#") and len(t) == 7:
        try:
            return tuple(int(t[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("sky must be navy, black, purple, blue or a colour like #101830")


def positive_int(text):
    try:
        v = int(text)
    except ValueError:
        v = 0
    if v < 1:
        raise argparse.ArgumentTypeError("%r is not a whole number of at least 1" % text)
    return v


def add_star_options(ap):
    """The options that decide what the sky looks like - identical in every script."""
    g = ap.add_argument_group("the stars")
    g.add_argument("--seed", type=int, default=1, help="which star field to make; another number = another sky (default 1)")
    g.add_argument("--density", type=float, default=1.0, help="how many stars, 1 = normal, 0.5 = half, 2 = twice (default 1)")
    g.add_argument("--speed", type=float, default=1.0, help="how fast they drift, 1 = normal, 0 = standing still (default 1)")
    g.add_argument("--frames", type=positive_int, default=60,
                   help="length of the loop in frames at %d per second; longer = harder to notice the loop (default 60)" % FPS)
    g.add_argument("--palette", choices=list(PALETTES), default="default", help="star colours (default: default)")
    g.add_argument("--sky", type=parse_sky, default=DEFAULT_SKY,
                   help="the faint haze along the bottom: navy (default), black, purple, blue or a colour like #101830")


def check_star_options(ap, a):
    if not 0.05 <= a.density <= 8:
        ap.error("--density must be between 0.05 and 8")
    if not 0 <= a.speed <= 6:
        ap.error("--speed must be between 0 and 6")
    if not 40 <= a.frames <= 400:
        ap.error("--frames must be between 40 and 400")

# --------------------------------------------------------------------------------------------
#  PNG files, written with nothing but the standard library
# --------------------------------------------------------------------------------------------


def _chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def png_bytes(width, height, rows, colour_type, extra=(), level=9):
    """rows: an iterable of 'height' byte strings (one per pixel row: RGB bytes, or palette indices)."""
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    out = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0))
    for kind, data in extra:
        out += _chunk(kind, data)
    return out + _chunk(b"IDAT", zlib.compress(raw, level)) + _chunk(b"IEND", b"")

# --------------------------------------------------------------------------------------------
#  Packing the tile into a web page
# --------------------------------------------------------------------------------------------
SHEET_COLS = 6             # frames per row in the sprite sheet


def sprite_sheet(tile, cols):
    """All frames of the tile in one transparent, palette-based PNG picture (the page cuts it up again)."""
    rows = -(-tile.frames // cols)
    empty = bytes(TILE_W)
    lines = []
    for r in range(rows):
        for y in range(TILE_H):
            parts = []
            for c in range(cols):
                f = r * cols + c
                parts.append(bytes(tile.index[f][y * TILE_W:(y + 1) * TILE_W]) if f < tile.frames else empty)
            lines.append(b"".join(parts))
    plte = b"".join(bytes(c) for c in tile.palette)
    return png_bytes(cols * TILE_W, rows * TILE_H, lines, 3, extra=[(b"PLTE", plte), (b"tRNS", b"\x00")])


def make_page(template, tile, sky, **extra):
    """Fill the blanks (written __LIKE_THIS__) of a page template."""
    png = sprite_sheet(tile, SHEET_COLS)
    fill = {"SHEET": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            "N": tile.frames, "COLS": SHEET_COLS, "TW": TILE_W, "TH": TILE_H, "LOOP": "%g" % (tile.frames / FPS),
            "SKY_START": int(round(SKY_START * 100)), "SKY_RGB": "%d,%d,%d" % tuple(sky)}
    fill.update(extra)
    html = template
    for key, value in fill.items():
        html = html.replace("__%s__" % key, str(value))
    return html


def write_text(path, text):
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as err:
        sys.exit("could not write %s: %s" % (path, err.strerror or err))

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Starfield live wallpaper (endless)</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: #000; cursor: none; }
  /* a very faint haze along the bottom of the screen (look for SKY in the build script to change it) */
  #haze { position: fixed; left: 0; top: 0; width: 100%; height: 100%;
          background: linear-gradient(to bottom, rgb(0,0,0) 0%, rgb(0,0,0) __SKY_START__%, rgb(__SKY_RGB__) 100%); }
  canvas { position: fixed; left: 0; top: 0; width: 100vw; height: 100vh; display: block; pointer-events: none; }
</style>
</head>
<body>
<div id="haze"></div>
<canvas id="stars"></canvas>
<script>
(() => {
"use strict";

// ---- the animation: __N__ frames of a __TW__ x __TH__ star tile, 50 ms each (a __LOOP__ s loop) ----------
// The frames sit in one sprite sheet (a small PNG, below), __COLS__ frames per row. Made by the build script.
const SHEET_SRC = "__SHEET__";
const TW = __TW__, TH = __TH__, N = __N__, COLS = __COLS__, FRAME_MS = 50;

// Optional URL parameters, added after the file name (for example  starfield-endless.html?life=3):
//   life=__LIFE__     average seconds before a patch of sky is re-rolled (smaller = more change)
//   fade=__FADE__   seconds a patch takes to change over to its new look (0 = instantly)
//   seed=12    fixed starting arrangement (default: a different one every time the page opens)
//   scale=2    draw every star 2 times bigger
const params = new URLSearchParams(location.search);
const num = (key, dflt, lo, hi) => {
  const v = parseFloat(params.get(key));
  return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : dflt;
};
const LIFE = num("life", __LIFE__, 0.5, 3600) * 1000;
const FADE = num("fade", __FADE__, 0, 10) * 1000;
const seed = params.has("seed") ? (parseInt(params.get("seed"), 10) >>> 0) : ((Math.random() * 4294967296) >>> 0);
const scaleOverride = params.has("scale") ? Math.max(1, parseInt(params.get("scale"), 10) || 1) : 0;

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const randint = (rng, lo, hi) => lo + Math.floor(rng() * (hi - lo + 1));   // inclusive

// What one patch shows: a window of the tile (sx, sy) at its own point (tau) in the loop.
function pick(rng, h) {
  return { sx: randint(rng, 0, TW - 1), sy: randint(rng, 0, TH - h), tau: randint(rng, 0, N - 1) };
}

// Repeating one small tile would show a grid and the same short loop everywhere. Here the screen is
// covered with randomly sized patches of the tile, and every patch is re-rolled at its own random
// moment: it changes over to a new window of the tile at a new point of the loop. Stars switch over in
// small blocks at random moments (never faded or dimmed), so a changing patch looks like stars simply
// turning on and off. At any time some patches are changing, so nothing on the screen repeats exactly.
function makeLayout(W, H, rng, now) {
  const minW = 160, maxW = 360, minH = 48, maxH = TH, jitter = 10;
  const cells = [];
  let y = 0;
  while (y < H) {
    const h = randint(rng, minH, maxH);
    let x = -randint(rng, 0, maxW - 1);
    while (x < W) {
      const w = randint(rng, minW, maxW);
      const ext = y > 0 ? randint(rng, 0, jitter) : 0;
      const ch = Math.min(h + ext, TH);
      cells.push({ x, y: y - (ch - h), w, h: ch, cur: pick(rng, ch), nxt: null,
                   fadeStart: 0, fadeDur: 1, k: 0, mox: 0, moy: 0, nextAt: now + rng() * LIFE * 1.5 });
      x += w;
    }
    y += h;
  }
  return cells;
}

const MAX_CELL_W = 360;
const B = 6;                        // blocks of 6x6 tile pixels (about one star) switch over one by one
const MBW = 60, MBH = 14;           // the switch-over pattern repeats every 60 x 14 blocks (360 x 84 tile pixels)
const canvas = document.getElementById("stars");
const ctx = canvas.getContext("2d");
const sheet = new Image();
let cells = [], S = 1, SW = 0, SH = 0, lastFrame = -1, lastNow = 0, t0 = performance.now();
let timer = 0, ready = false, drawn = 0, evo = null, avgMs = 0, lowPower = false;
let K = 10, theta = [], masks = [], scr = null;

function scratch() {
  const c = document.createElement("canvas");
  c.width = MAX_CELL_W * S; c.height = TH * S;
  const g = c.getContext("2d");
  g.imageSmoothingEnabled = false;
  return { c, g };
}

// masks[k] is opaque on the blocks that have switched over by step k (their random threshold is below
// k/K), k = 0..K. The pattern is drawn twice over in both directions so that any 360 x 80 piece of it,
// starting anywhere, is one drawImage call.
function buildMasks() {
  const r = mulberry32((seed ^ 0xA5A5A5A5) >>> 0);
  theta = Array.from({ length: MBW * MBH }, () => r());
  K = Math.max(1, Math.min(40, Math.round(FADE / FRAME_MS)));
  masks = [];
  for (let k = 0; k <= K; k++) {
    const m = document.createElement("canvas");
    m.width = 2 * MBW * B * S; m.height = 2 * MBH * B * S;
    const g = m.getContext("2d");
    g.fillStyle = "#000";
    for (let by = 0; by < 2 * MBH; by++)
      for (let bx = 0; bx < 2 * MBW; bx++)
        if (theta[(by % MBH) * MBW + (bx % MBW)] < k / K) g.fillRect(bx * B * S, by * B * S, B * S, B * S);
    masks.push(m);
  }
  scr = scratch();
}

function layout() {
  const dpr = window.devicePixelRatio || 1;
  S = scaleOverride || Math.max(1, Math.round(dpr));          // one tile pixel = S screen pixels
  canvas.width = Math.max(1, Math.round(window.innerWidth * dpr));
  canvas.height = Math.max(1, Math.round(window.innerHeight * dpr));
  ctx.imageSmoothingEnabled = false;
  SW = Math.ceil(canvas.width / S); SH = Math.ceil(canvas.height / S);
  buildMasks();
  const now = performance.now();
  cells = makeLayout(SW, SH, mulberry32(seed), now);
  evo = mulberry32((seed ^ 0x9E3779B9) >>> 0);                 // random stream for the re-rolls
  lastFrame = -1; lastNow = now;
  if (ready) render(now);
}

// Draw one window of the tile (starting at pixel dx, dy of context g).
function blit(g, c, L, T, dx, dy) {
  const tf = (T + L.tau) % N;
  const ox = (tf % COLS) * TW, oy = Math.floor(tf / COLS) * TH + L.sy;
  const a = Math.min(c.w, TW - L.sx);                          // the tile wraps sideways inside a patch
  g.drawImage(sheet, ox + L.sx, oy, a, c.h, dx, dy, a * S, c.h * S);
  if (c.w > a) g.drawImage(sheet, ox, oy, c.w - a, c.h, dx + a * S, dy, (c.w - a) * S, c.h * S);
}

// A patch half way through its change: the new window where the mask is on, the old one where it is off.
function mixed(c, T, k) {
  const w = c.w * S, h = c.h * S, px = c.x * S, py = c.y * S, m = masks[k], A = scr;
  const mx = c.mox * S, my = c.moy * S;                        // this patch's own shift of the pattern
  A.g.globalCompositeOperation = "source-over";                // the new window, kept only on switched blocks
  A.g.clearRect(0, 0, w, h);
  blit(A.g, c, c.nxt, T, 0, 0);
  A.g.globalCompositeOperation = "destination-in";
  A.g.drawImage(m, mx, my, w, h, 0, 0, w, h);
  blit(ctx, c, c.cur, T, px, py);                              // the old window, cut away on switched blocks
  ctx.globalCompositeOperation = "destination-out";
  ctx.drawImage(m, mx, my, w, h, px, py, w, h);
  ctx.globalCompositeOperation = "source-over";
  ctx.drawImage(A.c, 0, 0, w, h, px, py, w, h);                // put the two together
}

function settle(c, now) {                                      // the change is over: keep the new window
  c.cur = c.nxt; c.nxt = null; c.k = 0; c.nextAt = now + LIFE * (0.5 + evo());
}

function render(now) {
  const started = performance.now();
  const T = Math.floor((now - t0) / FRAME_MS);                 // frames since the page opened
  lastFrame = T; drawn++;
  if (now - lastNow > 1500) {                                  // back after a pause: do not re-roll everything at once
    for (const c of cells) {
      if (c.nxt) { c.cur = c.nxt; c.nxt = null; c.k = 0; }
      if (c.nextAt < now) c.nextAt = now + evo() * LIFE * 1.5;
    }
  }
  lastNow = now;
  for (const c of cells) {
    if (c.x >= SW || c.y >= SH || c.x + c.w <= 0 || c.y + c.h <= 0) continue;
    if (!c.nxt && now >= c.nextAt) {                           // time to re-roll this patch
      c.nxt = pick(evo, c.h); c.fadeStart = now; c.fadeDur = lowPower ? 0 : FADE * (0.7 + 0.6 * evo());
      c.mox = randint(evo, 0, MBW * B - 1); c.moy = randint(evo, 0, MBH * B - 1);
    }
    c.k = 0;
    if (c.nxt) {
      const k = Math.round(K * Math.min(1, (now - c.fadeStart) / Math.max(1, c.fadeDur)));
      if (k >= K || c.fadeDur < 1) settle(c, now); else c.k = k;
    }
    ctx.clearRect(c.x * S, c.y * S, c.w * S, c.h * S);         // a patch replaces whatever was under it
    if (c.k > 0) mixed(c, T, c.k);
    else blit(ctx, c, c.cur, T, c.x * S, c.y * S);
  }
  // On a slow machine give up the gradual change-over (patches then just swap) rather than hog the CPU.
  const spent = performance.now() - started;
  avgMs = drawn === 1 ? spent : avgMs * 0.95 + spent * 0.05;
  if (avgMs > 30 && drawn > 15) lowPower = true;
}

// One wake-up per frame (20 per second): sleep until the next 50 ms boundary, then draw.
function tick() {
  timer = setTimeout(tick, FRAME_MS - ((performance.now() - t0) % FRAME_MS) + 2);
  if (!ready || document.hidden) return;
  const now = performance.now();
  if (Math.floor((now - t0) / FRAME_MS) !== lastFrame) render(now);
}

function start() {
  ready = true;
  layout();
  tick();
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { clearTimeout(timer); tick(); } });
}

let resizeTimer = 0;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(layout, 150); });

sheet.onload = start;
sheet.src = SHEET_SRC;

// handy for testing / screenshots
window.__starfield = {
  layout: () => cells.map(c => ({ x: c.x, y: c.y, w: c.w, h: c.h, cur: { ...c.cur }, nxt: c.nxt && { ...c.nxt },
                                  k: c.k, mox: c.mox, moy: c.moy })),
  masks: () => ({ K, B, MBW, MBH, theta: theta.slice() }),
  size: () => [SW, SH, S],
  stop: () => clearTimeout(timer),
  renderAt: (ms) => render(t0 + ms),
  drawn: () => drawn, lowPower: () => lowPower, avgMs: () => avgMs,
  bench: (n) => { const a = performance.now(); for (let i = 0; i < n; i++) render(a + i * FRAME_MS); return (performance.now() - a) / n; },
};
})();
</script>
</body>
</html>
"""

DEFAULT_LIFE = 5           # average seconds before a patch of sky is re-rolled
DEFAULT_FADE = 0.6         # seconds a change-over takes


def main():
    ap = argparse.ArgumentParser(description="Make starfield-endless.html, a live starfield wallpaper that never repeats.")
    ap.add_argument("--out", default="starfield-endless.html", help="file to write (default starfield-endless.html)")
    ap.add_argument("--life", type=float, default=DEFAULT_LIFE,
                    help="average seconds before a patch of sky is re-rolled; the page address can change it later (default %g)" % DEFAULT_LIFE)
    ap.add_argument("--fade", type=float, default=DEFAULT_FADE,
                    help="seconds a change-over takes, 0 = instantly (default %g)" % DEFAULT_FADE)
    add_star_options(ap)
    a = ap.parse_args()
    check_star_options(ap, a)
    if not 0.5 <= a.life <= 3600:
        ap.error("--life must be between 0.5 and 3600 seconds")
    if not 0 <= a.fade <= 10:
        ap.error("--fade must be between 0 and 10 seconds")

    tile = make_tile(a.seed, a.frames, a.density, a.speed, a.palette)
    html = make_page(TEMPLATE, tile, a.sky, LIFE="%g" % a.life, FADE="%g" % a.fade)
    write_text(a.out, html)
    print("wrote %s (%.0f KB): %d frames = a %g second loop, %d star colours"
          % (a.out, len(html) / 1000.0, tile.frames, tile.frames / FPS, len(tile.palette) - 1))
    print("Open it in a browser, or see README.md for how to use it as your wallpaper.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nstopped")
