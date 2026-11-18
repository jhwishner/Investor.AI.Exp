"""Ivy grown around real letterforms.

Every earlier attempt scattered vines inside a box and hoped they would
interact with the type. They cannot: the generator had no idea where the
glyphs were, so vines could never hug a stroke or pass around one, and the
result always read as streaks lying across the words.

This module measures the type first. The wordmark is rasterised with the
same font file the browser loads (static/fonts), giving an ink mask; the
vines are then grown against that mask:

  * runners thread through the REAL gaps between letters
  * a runner is split at every ink boundary it crosses, and consecutive
    crossings alternate between the front and back layers -- so the vine
    genuinely passes behind one stroke and over the next
  * leaves are pushed out of dense ink so they decorate rather than smother

Geometry is built once as plain data, then rendered twice: to SVG for the
app, and to a PNG so the result can actually be looked at rather than
assumed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = Path(__file__).parent / "static" / "fonts" / "CormorantGaramond[wght].ttf"
FONT_WEIGHT = 500          # must match the CSS font-weight for the hero title
REF_SIZE = 200             # rasterisation size; all geometry is in these units

IVY = "#4E7F63"
ROSE = "#9C6D72"
GOLD = "#9c7b3f"
LEAF_SHADES = ("#41705A", "#5A8C6F", "#7BA88C")

_LEAF = (
    "M0,2 C-5,3 -10,5 -13,10 C-12,14 -10,15 -8,16 C-10,20 -13,23 -13,27 "
    "C-9,28 -5,29 -3,31 C-2,33 -1,34 0,36 C1,34 2,33 3,31 C5,29 9,28 13,27 "
    "C13,23 10,20 8,16 C10,15 12,14 13,10 C10,5 5,3 0,2 Z"
)
_LEAF_PTS = [(-5, 3), (-13, 10), (-8, 16), (-13, 27), (-3, 31), (0, 36),
             (3, 31), (13, 27), (8, 16), (13, 10), (5, 3)]


@dataclass
class Segment:
    points: list[tuple[float, float]]
    layer: str              # "back" | "front"
    width: float


@dataclass
class Leaf:
    x: float
    y: float
    rot: float
    scale: float
    shade: str
    layer: str


@dataclass
class Flower:
    x: float
    y: float
    scale: float
    rot: float
    kind: str               # "bloom" | "bud"
    layer: str


@dataclass
class Geometry:
    box: tuple[float, float, float, float]     # viewBox x,y,w,h
    ink_bbox: tuple[int, int, int, int]        # glyph bbox in raster coords
    segments: list[Segment] = field(default_factory=list)
    leaves: list[Leaf] = field(default_factory=list)
    flowers: list[Flower] = field(default_factory=list)


def _stable_id(*parts) -> str:
    """Content hash for the asset filename.

    Deliberately hashlib, not the builtin hash(): Python randomises string
    hashing per process, so a builtin-hash filename changes on every app
    restart and static/ fills up with identical orphaned renders.
    """
    return hashlib.md5("::".join(map(str, parts)).encode()).hexdigest()[:10]


def _prune_stale_assets(keep: set[str]) -> None:
    """Drop wordmark renders that no longer correspond to live content."""
    for old in STATIC_DIR.glob("wm-*.png"):
        if old.name not in keep:
            old.unlink(missing_ok=True)


def _font(size: int = REF_SIZE) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_PATH), size)
    try:
        f.set_variation_by_axes([FONT_WEIGHT])
    except Exception:
        pass                # static build: weight already baked in
    return f


def _ink_mask(text: str, pad: int = 260) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    font = _font()
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    x0, y0, x1, y1 = tmp.textbbox((0, 0), text, font=font)
    img = Image.new("L", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), 0)
    ImageDraw.Draw(img).text((pad - x0, pad - y0), text, font=font, fill=255)
    return np.array(img) > 110, (pad, pad, pad + (x1 - x0), pad + (y1 - y0))


def _letter_gaps(mask: np.ndarray, bbox) -> list[float]:
    """X centres of the blank columns between letter strokes."""
    x0, _, x1, _ = bbox
    cols = mask[:, x0:x1].any(axis=0)
    gaps, start = [], None
    for i, filled in enumerate(cols):
        if not filled and start is None:
            start = i
        elif filled and start is not None:
            if i - start >= 3:
                gaps.append(x0 + (start + i) / 2)
            start = None
    return gaps


def _catmull(points: list[tuple[float, float]], per_span: int = 18):
    """Smooth polyline through the given nodes."""
    if len(points) < 2:
        return list(points)
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        for s in range(per_span):
            t = s / per_span
            t2, t3 = t * t, t * t * t
            out.append((
                0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
            ))
    out.append(points[-1])
    return out


def _is_ink(mask: np.ndarray, x: float, y: float, r: int = 3) -> bool:
    h, w = mask.shape
    xi, yi = int(x), int(y)
    if not (0 <= xi < w and 0 <= yi < h):
        return False
    return bool(mask[max(0, yi - r):yi + r + 1, max(0, xi - r):xi + r + 1].any())


def build(text: str = "Ivy Investments", seed: str = "wordmark",
          runners: int = 4) -> Geometry:
    rng = random.Random(seed)
    mask, bbox = _ink_mask(text)
    x0, y0, x1, y1 = bbox
    gaps = _letter_gaps(mask, bbox)
    # Centre on the x-height band (the rows carrying most of the ink), NOT
    # on the bounding box: a single descender like the 'y' in "Ivy" drags
    # the bbox centre well below the body of the type, which pushed every
    # runner underneath the word and left the letters bare above.
    row_ink = mask[y0:y1, x0:x1].sum(axis=1)
    busy = np.where(row_ink > row_ink.max() * 0.22)[0]
    mid = y0 + float(busy.mean()) if len(busy) else (y0 + y1) / 2
    # Amplitude still references the FULL cap height -- deriving it from
    # the narrow x-height band squashed every runner into one tight line.
    tall = y1 - y0

    pad_x, pad_y = 150, 210
    geo = Geometry(box=(x0 - pad_x, y0 - pad_y,
                        (x1 - x0) + pad_x * 2, (y1 - y0) + pad_y * 2),
                   ink_bbox=bbox)

    for r in range(runners):
        # Nodes sit in the real gaps between letters, alternating above and
        # below the middle of the type, so the runner threads between the
        # strokes instead of lying across them.
        # Each runner is handed its own stretch of the word, so foliage is
        # spread across the whole wordmark instead of piling into the middle.
        if len(gaps) < 3:
            continue
        share = len(gaps) / runners
        lo = int(r * share * rng.uniform(0.75, 1.0))
        hi = min(len(gaps), max(lo + 3, int((r + 1.6) * share)))
        chosen = gaps[lo:hi]
        if len(chosen) < 3:
            continue

        up = rng.random() < 0.5
        amp = tall * rng.uniform(0.16, 0.30)
        # Own vertical centre per runner: sharing one centre stacks them
        # into a single horizontal band across the middle of the word.
        centre = mid + tall * rng.uniform(-0.26, 0.26)
        nodes = []
        entry = chosen[0] - rng.uniform(40, 95)
        nodes.append((entry, centre + rng.uniform(-0.12, 0.12) * tall))
        for g in chosen:
            nodes.append((g + rng.uniform(-14, 14),
                          centre + (-amp if up else amp) * rng.uniform(0.75, 1.15)))
            up = not up
        exit_x = chosen[-1] + rng.uniform(40, 95)
        nodes.append((exit_x, centre + rng.uniform(-0.15, 0.30) * tall))

        path = _catmull(nodes)
        stroke = rng.uniform(2.0, 3.0)

        # Split at every ink boundary; alternate layer on each crossing so
        # the vine passes behind one stroke and in front of the next.
        crossing = 0
        cur: list[tuple[float, float]] = []
        cur_ink = _is_ink(mask, *path[0])
        for pt in path:
            ink = _is_ink(mask, *pt)
            if ink != cur_ink:
                cur.append(pt)
                if len(cur) > 1:
                    layer = "back"
                    if cur_ink:
                        layer = "front" if crossing % 2 == 0 else "back"
                        crossing += 1
                    geo.segments.append(Segment(cur, layer, stroke))
                cur = [pt]
                cur_ink = ink
            else:
                cur.append(pt)
        if len(cur) > 1:
            layer = "back"
            if cur_ink:
                layer = "front" if crossing % 2 == 0 else "back"
            geo.segments.append(Segment(cur, layer, stroke))

        # Foliage, kept out of dense ink so the type stays readable.
        n_leaves = rng.randint(14, 20)
        for li in range(n_leaves):
            frac = (li + rng.uniform(0.15, 0.85)) / n_leaves
            p = path[min(len(path) - 1, int(frac * len(path)))]
            jx = p[0] + rng.uniform(-13, 13)
            jy = p[1] + rng.uniform(-13, 13)
            if _is_ink(mask, jx, jy, r=8) and rng.random() < 0.72:
                continue
            geo.leaves.append(Leaf(
                jx, jy,
                max(-70.0, min(70.0, rng.gauss(0, 26))),
                rng.uniform(0.42, 0.78),
                rng.choice(LEAF_SHADES),
                "front" if rng.random() < 0.32 else "back",
            ))

        # A tendril and a drooping tail off the exit.
        tail = [(exit_x, nodes[-1][1])]
        ty = nodes[-1][1]
        tx = exit_x
        for _ in range(rng.randint(2, 4)):
            tx += rng.uniform(-22, 22)
            ty += rng.uniform(30, 55)
            tail.append((tx, ty))
        geo.segments.append(Segment(_catmull(tail), "back", stroke * 0.7))
        tail_path = _catmull(tail)
        for ti in range(rng.randint(7, 11)):
            p = tail_path[min(len(tail_path) - 1, int((ti + 0.4) / 11 * len(tail_path)))]
            geo.leaves.append(Leaf(p[0] + rng.uniform(-16, 16), p[1] + rng.uniform(-20, 20),
                                   max(-70.0, min(70.0, rng.gauss(0, 24))),
                                   rng.uniform(0.38, 0.62), rng.choice(LEAF_SHADES), "back"))

    for _ in range(rng.randint(3, 5)):
        p = rng.choice(geo.leaves)
        geo.flowers.append(Flower(p.x + rng.uniform(-20, 20), p.y + rng.uniform(-16, 16),
                                  rng.uniform(0.6, 1.0), rng.uniform(0, 360),
                                  "bloom" if rng.random() < 0.6 else "bud", p.layer))
    return geo


# --- renderers ---------------------------------------------------------------

_LEAF_DEFS = f'<defs><path id="iv" d="{_LEAF}"/></defs>'


def _poly_d(points) -> str:
    return "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in points)


def _bloom_svg(f: Flower) -> str:
    petals = "".join(
        f'<path d="M0,0 C7,-5 14,0 9,7 C5,11 -3,9 0,0 Z" transform="rotate({a})"/>'
        for a in (0, 72, 144, 216, 288))
    return (f'<g transform="translate({f.x:.0f},{f.y:.0f}) rotate({f.rot:.0f}) '
            f'scale({f.scale:.2f})" fill="{ROSE}"><circle r="3.2" fill="{GOLD}"/>{petals}</g>')


def _bud_svg(f: Flower) -> str:
    return (f'<g transform="translate({f.x:.0f},{f.y:.0f}) rotate({f.rot:.0f}) scale({f.scale:.2f})">'
            f'<path d="M0,0 C7,-9 7,-20 0,-27 C-7,-20 -7,-9 0,0 Z" fill="{ROSE}"/>'
            f'<path d="M-2,-2 C-8,-4 -11,2 -6,6 Z" fill="{IVY}"/>'
            f'<path d="M2,-2 C8,-4 11,2 6,6 Z" fill="{IVY}"/></g>')


def to_svg(geo: Geometry, layer: str, opacity: float = 0.85) -> str:
    x, y, w, h = geo.box
    parts = []
    for s in geo.segments:
        if s.layer != layer:
            continue
        parts.append(f'<path d="{_poly_d(s.points)}" fill="none" stroke="{IVY}" '
                     f'stroke-width="{s.width:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
    for lf in geo.leaves:
        if lf.layer != layer:
            continue
        parts.append(
            f'<g transform="translate({lf.x:.0f},{lf.y:.0f}) rotate({lf.rot:.0f}) scale({lf.scale:.2f})">'
            f'<path d="M0,0 Q1,4 0,7" fill="none" stroke="{lf.shade}" stroke-width="1.6" stroke-linecap="round"/>'
            f'<use href="#iv" fill="{lf.shade}" transform="translate(0,7)"/></g>')
    for fl in geo.flowers:
        if fl.layer != layer:
            continue
        parts.append(_bloom_svg(fl) if fl.kind == "bloom" else _bud_svg(fl))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.0f} {y:.0f} {w:.0f} {h:.0f}" '
            f'width="{w:.0f}" height="{h:.0f}" role="presentation" aria-hidden="true">'
            f'{_LEAF_DEFS}<g opacity="{opacity}">{"".join(parts)}</g></svg>')


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _draw_layer(draw: ImageDraw.ImageDraw, geo: Geometry, layer: str, ox: float, oy: float):
    for s in geo.segments:
        if s.layer != layer:
            continue
        draw.line([(p[0] - ox, p[1] - oy) for p in s.points],
                  fill=_hex(IVY), width=max(1, int(s.width)), joint="curve")
    for lf in geo.leaves:
        if lf.layer != layer:
            continue
        a = math.radians(lf.rot)
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for px, py in _LEAF_PTS:
            sx, sy = px * lf.scale, (py + 7) * lf.scale
            pts.append((lf.x - ox + sx * ca - sy * sa, lf.y - oy + sx * sa + sy * ca))
        draw.polygon(pts, fill=_hex(lf.shade))
        draw.line([(lf.x - ox, lf.y - oy),
                   (lf.x - ox - 7 * lf.scale * sa, lf.y - oy + 7 * lf.scale * ca)],
                  fill=_hex(lf.shade), width=max(1, int(1.6 * lf.scale)))
    for fl in geo.flowers:
        if fl.layer != layer:
            continue
        rr = 7 * fl.scale
        draw.ellipse([fl.x - ox - rr, fl.y - oy - rr, fl.x - ox + rr, fl.y - oy + rr], fill=_hex(ROSE))
        draw.ellipse([fl.x - ox - rr * .3, fl.y - oy - rr * .3,
                      fl.x - ox + rr * .3, fl.y - oy + rr * .3], fill=_hex(GOLD))


def to_png(geo: Geometry, text: str = "Ivy Investments", path: str = "/tmp/wordmark.png",
           bg=(250, 250, 250), ink=(24, 24, 27)):
    """Composite back ivy -> type -> front ivy, exactly as the page stacks
    them. This exists so the output can be inspected instead of assumed."""
    x, y, w, h = geo.box
    img = Image.new("RGB", (int(w), int(h)), bg)
    d = ImageDraw.Draw(img)
    _draw_layer(d, geo, "back", x, y)
    bx, by, _, _ = geo.ink_bbox
    font = _font()
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    tx0, ty0, _, _ = tmp.textbbox((0, 0), text, font=font)
    d.text((bx - x - tx0, by - y - ty0), text, font=font, fill=ink)
    _draw_layer(d, geo, "front", x, y)
    img.save(path)
    return path


# --- composed asset ----------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"


def render_asset(text: str = "Ivy Investments", seed: str = "wordmark",
                 runners: int = 5, scale: float = 2.0,
                 ink: tuple = (24, 24, 27), filename: str | None = None,
                 supersample: int = 2) -> tuple[str, float]:
    """Composite ivy + type into a transparent PNG under static/.

    Composed server-side and served as a file rather than assembled in the
    browser for two reasons: the ivy is positioned against measured glyph
    geometry, so any drift between what was measured and what the browser
    lays out would put vines in the wrong place; and a static file is
    fetched once and cached, instead of a ~40KB data URI riding along with
    every Streamlit rerun.

    Drawn at `supersample` times the target size and then reduced with a
    Lanczos filter. PIL rasterises lines and polygons with no antialiasing,
    so drawing straight to the final size leaves every vine and leaf edge
    stair-stepped; downsampling supplies the antialiasing. Text is already
    antialiased by FreeType and survives the reduction cleanly.

    Returns (filename, aspect_ratio).
    """
    geo = build(text, seed, runners)
    x, y, w, h = geo.box
    W, H = int(w * scale), int(h * scale)
    draw_scale = scale * supersample
    img = Image.new("RGBA", (int(w * draw_scale), int(h * draw_scale)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    class _S:
        """Scale-aware proxy so the shared draw code needs no changes."""
        def __init__(self, dd, k): self.d, self.k = dd, k
        def line(self, pts, fill, width, joint=None):
            self.d.line([(px * self.k, py * self.k) for px, py in pts],
                        fill=fill, width=max(1, int(width * self.k)), joint=joint)
        def polygon(self, pts, fill):
            self.d.polygon([(px * self.k, py * self.k) for px, py in pts], fill=fill)
        def ellipse(self, box, fill):
            self.d.ellipse([v * self.k for v in box], fill=fill)

    sd = _S(d, draw_scale)
    _draw_layer(sd, geo, "back", x, y)

    bx, by, _, _ = geo.ink_bbox
    font = _font(int(REF_SIZE * draw_scale))
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    tx0, ty0, _, _ = tmp.textbbox((0, 0), text, font=font)
    d.text(((bx - x) * draw_scale - tx0, (by - y) * draw_scale - ty0), text, font=font, fill=ink)

    _draw_layer(sd, geo, "front", x, y)

    if supersample > 1:
        img = img.resize((W, H), Image.LANCZOS)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    name = filename or f"wordmark-{_stable_id(text, seed, runners, scale, supersample)}.png"
    img.save(STATIC_DIR / name, optimize=True)
    return name, w / h


@lru_cache(maxsize=8)
def hero_asset(text: str, seed: str = "hero", runners: int = 5,
               scale: float = 2.0) -> tuple[str, float]:
    """Cached wrapper -- one render per distinct line of text per process."""
    safe = "".join(c for c in text if c.isalnum())[:24].lower() or "wordmark"
    return render_asset(text, seed=f"{seed}::{text}", runners=runners, scale=scale,
                        filename=f"wm-{safe}-{_stable_id(text, seed, runners, scale)}.png")
