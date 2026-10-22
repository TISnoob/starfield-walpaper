#!/usr/bin/env python3
"""
build-walpaper-png.py - make a starfield picture (PNG) to use as an ordinary desktop background.

Run it:
    python3 build-walpaper-png.py               (on Windows:  py build-walpaper-png.py)

That writes starfield_1920x1080.png: one still picture of the starfield, exactly as big as
your screen if you give it your screen's size:
    python3 build-walpaper-png.py --width 2560 --height 1440
    python3 build-walpaper-png.py --width 3840 --height 2160 --scale 2     # 4K, stars 2x bigger
    python3 build-walpaper-png.py --width 2880 --height 1800 --scale 2     # a Retina MacBook

A still picture does not move, but it works everywhere with no extra program: set it as your
background in the system settings. Want a different one now and then? Make several:
    python3 build-walpaper-png.py --count 10    # ten different pictures (starfield_1920x1080_01.png ...)
then pick the folder in the "slideshow" option of your system's background settings.

This script needs only Python 3.8 or newer (nothing to install).

All the options:
    --width, --height   size of the picture in pixels (default 1920 x 1080)
    --scale N           draw every star N times bigger, for very sharp screens (default 1)
    --count N           how many different pictures to make (default 1)
    --frame N           which moment of the 3-second animation the picture shows (default 0)
    --out NAME.png      file name (default starfield_WIDTHxHEIGHT.png)
    --seed, --density, --speed, --frames, --palette, --sky      what the stars look like (see --help)
    --layout-seed       another arrangement of the patches the screen is made of
"""
import argparse
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
#  From the small tile to a whole screen. A plain repeat of the tile would show a grid and every
#  star would flash in sync, so the screen is covered with randomly sized "patches" of the tile,
#  each looking at its own spot of the tile and at its own moment of the loop.
#  (The web pages do exactly the same, with the same numbers: the same seed gives the same layout.)
# --------------------------------------------------------------------------------------------
def make_layout(width, height, frames, seed):
    """Patches covering width x height (in tile pixels). Each is (x, y, w, h, sx, sy, tau):
    it shows tile columns sx.. (wrapping around), tile rows sy.., at loop frame (f + tau)."""
    rng = Rng(seed)
    min_w, max_w, min_h, max_h, jitter = 240, TILE_W, 48, TILE_H, 10
    cells = []
    y = 0
    while y < height:
        h = rng.randint(min_h, max_h)
        x = -rng.randint(0, max_w - 1)
        while x < width:
            w = rng.randint(min_w, max_w)
            ext = rng.randint(0, jitter) if y > 0 else 0     # rows overlap a little, so seams are not straight
            ch = min(h + ext, TILE_H)
            sx = rng.randint(0, TILE_W - 1)
            sy = rng.randint(0, TILE_H - ch)
            tau = rng.randint(0, frames - 1)
            cells.append((x, y - (ch - h), w, ch, sx, sy, tau))
            x += w
        y += h
    return cells


BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def haze_background(width, height, pad_w, pad_h, sky):
    """The faint haze as raw RGB rows (dithered, so the very slow gradient shows no steps)."""
    rows = []
    black = bytes(pad_w * 3)
    for y in range(pad_h):
        t = ((y + 0.5) / height - SKY_START) / (1.0 - SKY_START)
        t = 0.0 if t < 0 else 1.0 if t > 1 else t
        if t == 0.0 or not any(sky):
            rows.append(black)
            continue
        pattern = bytearray()
        for x in range(4):
            th = (BAYER[y % 4][x] + 0.5) / 16.0
            pattern += bytes(int(c * t + th) for c in sky)
        rows.append((bytes(pattern) * (pad_w // 4 + 1))[:pad_w * 3])
    return b"".join(rows)


class Screen(object):
    """Draws frames of the wallpaper as plain RGB bytes. `scale` = how many screen pixels one tile pixel covers."""

    def __init__(self, tile, width, height, scale=1, layout_seed=LAYOUT_SEED, sky=DEFAULT_SKY):
        self.tile, self.width, self.height, self.scale = tile, width, height, scale
        self.sw, self.sh = -(-width // scale), -(-height // scale)        # screen size in tile pixels
        self.pad_w, self.pad_h = self.sw * scale, self.sh * scale          # (may be a bit larger than the screen)
        self.cells = make_layout(self.sw, self.sh, tile.frames, layout_seed)
        self.background = haze_background(width, height, self.pad_w, self.pad_h, sky)
        colours = [bytes(c) * scale for c in tile.palette]
        # for every frame and every tile row: the lit pixels as (column, colour bytes), left to right
        self.lit = []
        for plane in tile.index:
            rows = []
            for y in range(TILE_H):
                row = plane[y * TILE_W:(y + 1) * TILE_W]
                rows.append([(x, colours[v]) for x, v in enumerate(row) if v] if any(row) else [])
            self.lit.append(rows)

    def frame(self, f):
        """Frame number f (0 to tile.frames - 1) as RGB bytes, width x height x 3."""
        S, sw, sh, stride = self.scale, self.sw, self.sh, self.pad_w * 3
        bg = self.background
        buf = bytearray(bg)
        n = self.tile.frames
        for cx, cy, cw, ch, sx, sy, tau in self.cells:
            if cx >= sw or cy >= sh or cx + cw <= 0 or cy + ch <= 0:
                continue
            lit = self.lit[(f + tau) % n]
            x0, x1 = max(cx, 0) * S * 3, min(cx + cw, sw) * S * 3
            for r in range(ch):
                ty = cy + r
                if ty < 0 or ty >= sh:
                    continue
                first = ty * S * stride
                for k in range(S):                                         # a patch replaces whatever was under it
                    a = first + k * stride
                    buf[a + x0:a + x1] = bg[a + x0:a + x1]
                for tx, colour in lit[sy + r]:
                    dx = tx - sx
                    if dx < 0:
                        dx += TILE_W                                      # the tile wraps around sideways
                    if dx >= cw:
                        continue
                    x = cx + dx
                    if x < 0 or x >= sw:
                        continue
                    a = first + x * S * 3
                    for k in range(S):
                        buf[a:a + S * 3] = colour
                        a += stride
        if self.pad_w == self.width and self.pad_h == self.height:
            return buf
        out = bytearray()
        for y in range(self.height):
            out += buf[y * stride:y * stride + self.width * 3]
        return out


def write_png_rgb(path, width, height, rows):
    data = png_bytes(width, height, rows, 2, level=6)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as err:
        sys.exit("could not write %s: %s" % (path, err.strerror or err))


def main():
    ap = argparse.ArgumentParser(description="Make a starfield picture (PNG) for your desktop background.")
    ap.add_argument("--width", type=positive_int, default=1920, help="picture width in pixels (default 1920)")
    ap.add_argument("--height", type=positive_int, default=1080, help="picture height in pixels (default 1080)")
    ap.add_argument("--scale", type=positive_int, default=1,
                    help="draw every star this many times bigger; use 2 on very sharp (HiDPI / Retina) screens (default 1)")
    ap.add_argument("--count", type=positive_int, default=1, help="how many different pictures to make (default 1)")
    ap.add_argument("--frame", type=int, default=0,
                    help="which moment of the loop the first picture shows, 0 up to frames-1 (default 0)")
    ap.add_argument("--out", default=None, help="file name (default starfield_WIDTHxHEIGHT.png)")
    ap.add_argument("--layout-seed", type=int, default=LAYOUT_SEED,
                    help="arrangement of the patches the screen is made of (default %d)" % LAYOUT_SEED)
    add_star_options(ap)
    a = ap.parse_args()
    check_star_options(ap, a)
    if not (16 <= a.width <= 16384 and 16 <= a.height <= 16384):
        ap.error("--width and --height must be between 16 and 16384")
    if a.scale > 16:
        ap.error("--scale must be between 1 and 16")
    if a.count > 500:
        ap.error("--count must be 500 or less")

    out = a.out or "starfield_%dx%d.png" % (a.width, a.height)
    stem = out[:-4] if out.lower().endswith(".png") else out
    tile = make_tile(a.seed, a.frames, a.density, a.speed, a.palette)
    for i in range(a.count):
        screen = Screen(tile, a.width, a.height, a.scale, a.layout_seed + i, a.sky)
        frame = screen.frame((a.frame + 13 * i) % tile.frames)
        path = out if a.count == 1 else "%s_%02d.png" % (stem, i + 1)
        stride = a.width * 3
        write_png_rgb(path, a.width, a.height, (frame[y * stride:(y + 1) * stride] for y in range(a.height)))
        print("wrote %s" % path)
    print("Set it as your desktop background in your system's settings (see README.md).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nstopped")
