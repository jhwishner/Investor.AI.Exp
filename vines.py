"""Procedural ivy-and-rose vine artwork for the page background.

Pure Python -- no Streamlit, no I/O -- so it's independently testable (see
tests/test_vines.py). theme.py is the only consumer; it wraps the output in
CSS and injects it. Kept at the project root alongside theme.py because
it's presentation, not business logic (investor_ai/ stays reserved for the
market/portfolio code).

WHY PROCEDURAL: a single hand-drawn vine repeated on every page reads as
wallpaper -- the eye recognizes the repeat and it stops feeling like
growth. Instead every page derives its own vine from its name: different
wander, leaf density, offshoots, rose count, thickness, and repeat length.
Same page always looks the same (the seed is the page name, so it's stable
across reruns and refreshes); different pages never match.

THE SEAM GUARANTEE: the vine's centerline is a sum of sine harmonics whose
frequencies are all WHOLE numbers of waves per tile:

    x(t) = cx + sum_i  A_i * sin(2*pi*k_i*t + phase_i),   k_i integer

At t=0 and t=1 every term returns to the same value AND the same slope, so
x(0) == x(1) and x'(0) == x'(1). Tiling the artwork vertically therefore
joins with no step and no kink -- one unbroken vine down a page of any
length. Summing several harmonics (rather than the single sine this
started as) is what makes the line wander irregularly instead of tracing an
obviously mechanical S-curve, without giving up that guarantee.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache

# --- palette (matches .streamlit/config.toml) --------------------------------

IVY = "#047857"
ROSE = "#7a3b42"
GOLD = "#9c7b3f"

# Approved "Faded" strength: the ivy line survives being read through
# because a stroke stays legible when faint; the filled rose muddies faster
# at the same opacity, so it sits lower.
IVY_OPACITY = 0.08
ROSE_OPACITY = 0.05

# A real ivy leaf (Hedera helix) is palmately LOBED -- five points, the
# central one longest, with deep sinuses between and a cordate base. The
# earlier shape here was a plain teardrop, which is what made the foliage
# read as generic rather than as ivy. Drawn growing along +y from a stem at
# the origin, so a rotation places it correctly.
_LEAF = (
    "M0,2 "
    "C-5,3 -10,5 -13,10 "      # broad left basal lobe, rounded tip
    "C-12,14 -10,15 -8,16 "    # shallow sinus -- a deep notch here is what
    "C-10,20 -13,23 -13,27 "   # made the leaf read as a spiky star
    "C-9,28 -5,29 -3,31 "      # shallow sinus
    "C-2,33 -1,34 0,36 "       # central lobe
    "C1,34 2,33 3,31 "         # mirrored back down the right side
    "C5,29 9,28 13,27 "
    "C13,23 10,20 8,16 "
    "C10,15 12,14 13,10 "
    "C10,5 5,3 0,2 Z"
)

# Emitted once per SVG; every leaf then references it by id instead of
# repeating ~200 characters of path data. With 80+ leaves in the arch
# that is the difference between a ~57KB and a ~30KB data URI, and this
# CSS is re-sent on every Streamlit rerun.
_LEAF_DEFS = '<defs><path id="iv" d="' + _LEAF + '"/></defs>'

# Foliage is never one flat colour. Three steps of the same green give the
# canopy some depth without introducing a second hue.
_LEAF_SHADES = ("#03583F", IVY, "#0E9A6B")

TILE_WIDTH = 220.0
_BEZIER_SEGMENTS = 24


class _Meander:
    """The vine's centerline: a sum of integer-frequency sine harmonics.

    Integer frequencies are what make the tile seamless -- see the module
    docstring. Amplitudes are normalized so the line always fits the tile
    regardless of which harmonics were drawn.
    """

    def __init__(self, rng: random.Random, height: float, max_amp: float, center: float):
        self.height = height
        self.center = center
        count = rng.choice((2, 3, 3, 4))
        freqs = rng.sample([1, 2, 3, 4, 5], count)
        amps = [rng.uniform(0.35, 1.0) / (f ** 0.65) for f in freqs]
        # Normalize to the worst case (all harmonics peaking together) so the
        # vine provably cannot wander outside the tile.
        scale = max_amp / sum(amps)
        self.terms = [
            (a * scale, f, rng.uniform(0, 2 * math.pi))
            for a, f in zip(amps, freqs)
        ]

    def x(self, t: float) -> float:
        return self.center + sum(
            a * math.sin(2 * math.pi * f * t + p) for a, f, p in self.terms
        )

    def dx(self, t: float) -> float:
        return sum(
            a * 2 * math.pi * f * math.cos(2 * math.pi * f * t + p)
            for a, f, p in self.terms
        )

    def point(self, t: float) -> tuple[float, float]:
        return self.x(t), self.height * t

    def tangent_deg(self, t: float) -> float:
        return math.degrees(math.atan2(self.height, self.dx(t)))

    def path_d(self) -> str:
        """Hermite -> cubic bezier sampling of the centerline."""
        px, py = self.point(0.0)
        parts = [f"M{px:.2f},{py:.2f}"]
        for i in range(_BEZIER_SEGMENTS):
            ta, tb = i / _BEZIER_SEGMENTS, (i + 1) / _BEZIER_SEGMENTS
            ax, ay = self.point(ta)
            bx, by = self.point(tb)
            h = (tb - ta) / 3.0
            c1x, c1y = ax + self.dx(ta) * h, ay + self.height * h
            c2x, c2y = bx - self.dx(tb) * h, by - self.height * h
            parts.append(f"C{c1x:.2f},{c1y:.2f} {c2x:.2f},{c2y:.2f} {bx:.2f},{by:.2f}")
        return " ".join(parts)


def _leaf(x: float, y: float, rot: float, scale: float, rng: random.Random | None = None) -> str:
    """A leaf JOINED to the vine by a petiole (leaf stalk).

    The stalk is the whole point: without it the blade sits at a bare point
    on the curve and reads as a sticker placed near the vine rather than
    something growing out of it. Both stalk and blade are emitted inside one
    transformed group, so the join is exact by construction rather than by
    computing world coordinates and hoping they line up.
    """
    # Coordinates are rounded hard and the stalk uses a single quadratic
    # control point: at the scale these render (a stalk is a few pixels)
    # more precision is invisible, and with 200+ leaves per document the
    # difference shows up in the stylesheet shipped on every rerun.
    rng = rng or random
    stalk = rng.uniform(4.0, 9.0)
    shade = rng.choice(_LEAF_SHADES)
    return (
        f'<g transform="translate({x:.0f},{y:.0f}) rotate({rot:.0f}) scale({scale:.2f})">'
        f'<path d="M0,0 Q{rng.uniform(-2, 2):.1f},{stalk * 0.6:.1f} 0,{stalk:.1f}" '
        f'fill="none" stroke="{shade}" stroke-width="1.5" stroke-linecap="round"/>'
        f'<use href="#iv" fill="{shade}" transform="translate(0,{stalk:.1f})"/>'
        f'</g>'
    )


def _cubic_subpath(p0, p1, p2, p3, t0: float, t1: float, steps: int = 14) -> str:
    """Polyline along part of a cubic -- used to overdraw a vine's lower
    section at a heavier weight so it tapers toward the tip. A constant
    stroke width is one of the things that reads as 'drawn line' rather
    than 'stem'."""
    pts = [_cubic_point(p0, p1, p2, p3, t0 + (t1 - t0) * i / steps) for i in range(steps + 1)]
    head = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    return head + "".join(f" L{x:.1f},{y:.1f}" for x, y in pts[1:])


def _leaves_along(rng, meander, density, t_start=0.0, t_end=1.0):
    """Leaves at jittered intervals, mostly alternating sides.

    Even spacing and strict alternation are the two things that make
    generated foliage look machine-made, so both are perturbed: gaps vary,
    and a leaf occasionally repeats the previous side to form a small
    cluster the way real growth does.
    """
    out = []
    span = t_end - t_start
    count = max(1, int(density * span))
    side = rng.choice((1, -1))
    t = t_start + rng.uniform(0.2, 0.8) * (span / count)
    for _ in range(count):
        if t >= t_end:
            break
        x, y = meander.point(t)
        phi = meander.tangent_deg(t)
        if rng.random() < 0.78:          # usually alternate, sometimes cluster
            side = -side
        rot = (phi if side > 0 else phi - 180) + side * rng.uniform(10, 38)
        out.append(_leaf(x, y, rot, rng.uniform(0.5, 0.95), rng))
        t += (span / count) * rng.uniform(0.55, 1.5)
    return out


def _offshoot(rng, meander, t):
    """A short secondary branch leaving the main vine, with its own leaves.

    Branching is most of what separates "a vine" from "a wavy line".
    """
    x, y = meander.point(t)
    phi = meander.tangent_deg(t)
    side = rng.choice((1, -1))
    length = rng.uniform(26, 58)
    curl = rng.uniform(0.4, 1.1)
    d = (f"M0,0 C{length * 0.35:.1f},{-8 * curl * side:.1f} "
         f"{length * 0.7:.1f},{6 * curl * side:.1f} {length:.1f},{-2 * curl * side:.1f}")
    rot = phi + (90 if side > 0 else -90) + rng.uniform(-24, 24)
    parts = [f'<g transform="translate({x:.2f},{y:.2f}) rotate({rot:.1f})">',
             f'<path d="{d}" fill="none" stroke="{IVY}" '
             f'stroke-width="{rng.uniform(1.5, 2.1):.1f}" stroke-linecap="round"/>']
    for i in range(rng.randint(1, 3)):
        f = (i + 1) / 4.0 + rng.uniform(-0.08, 0.08)
        parts.append(_leaf(length * f, -2 * curl * side * f,
                           rng.uniform(-160, 160), rng.uniform(0.4, 0.7), rng))
    parts.append("</g>")
    return "".join(parts)


def _tendril(rng, meander, t):
    x, y = meander.point(t)
    phi = meander.tangent_deg(t)
    s = rng.uniform(0.7, 1.3)
    return (f'<path d="M0,0 C14,-4 22,6 12,12 C5,16 0,8 7,5" fill="none" '
            f'stroke="{IVY}" stroke-width="2.1" stroke-linecap="round" '
            f'transform="translate({x:.2f},{y:.2f}) rotate({phi + rng.uniform(-30, 30):.1f}) '
            f'scale({s:.2f})"/>')


def _bloom(x, y, s, rot):
    petals = "".join(
        f'<path d="M0,0 C7,-5 14,0 9,7 C5,11 -3,9 0,0 Z" transform="rotate({a})"/>'
        for a in (0, 72, 144, 216, 288)
    )
    return (f'<g transform="translate({x:.2f},{y:.2f}) rotate({rot:.1f}) scale({s:.2f})" '
            f'fill="{ROSE}"><circle r="3.2" fill="{GOLD}"/>{petals}</g>')


def _bud(x, y, rot, s):
    return (f'<g transform="translate({x:.2f},{y:.2f}) rotate({rot:.1f}) scale({s:.2f})">'
            f'<path d="M0,0 C7,-9 7,-20 0,-27 C-7,-20 -7,-9 0,0 Z" fill="{ROSE}"/>'
            f'<path d="M-2,-2 C-8,-4 -11,2 -6,6 Z" fill="{IVY}"/>'
            f'<path d="M2,-2 C8,-4 11,2 6,6 Z" fill="{IVY}"/></g>')


def _roses(rng, meander, count):
    out = []
    for _ in range(count):
        t = rng.random()
        x, y = meander.point(t)
        phi = meander.tangent_deg(t)
        off = rng.uniform(12, 26) * rng.choice((1, -1))
        nx = math.cos(math.radians(phi + 90)) * off
        ny = math.sin(math.radians(phi + 90)) * off
        if rng.random() < 0.6:
            out.append(_bloom(x + nx, y + ny, rng.uniform(0.85, 1.25), rng.uniform(0, 360)))
        else:
            out.append(_bud(x + nx, y + ny, phi + rng.uniform(-30, 30), rng.uniform(0.7, 1.0)))
    return out


def build_vine(seed: str, mirrored: bool = False) -> tuple[str, float]:
    """One page-margin vine, fully determined by `seed`.

    Returns (svg, tile_height). The height is returned rather than
    recomputed by a second function replaying the same RNG -- CSS needs it
    for background-size, and re-deriving it elsewhere would desync silently
    the moment another random draw is added ahead of it here.

    Everything a viewer would read as "how much ivy is on this page" varies
    here: repeat length, how far it wanders, stroke weight, leaf density,
    how many offshoots and roses.
    """
    rng = random.Random(seed)

    height = rng.uniform(900, 1650)          # repeat length ("how long")
    max_amp = rng.uniform(38, 72)            # how far it wanders
    center = rng.uniform(78, 108)
    meander = _Meander(rng, height, max_amp, center)

    stroke = rng.uniform(2.1, 3.0)
    leaf_density = rng.uniform(9, 22)        # leaves per full tile ("how much")

    ivy_bits = [
        f'<path d="{meander.path_d()}" fill="none" stroke="{IVY}" '
        f'stroke-width="{stroke:.2f}" stroke-linecap="round"/>'
    ]
    for _ in range(rng.randint(0, 4)):
        ivy_bits.append(_offshoot(rng, meander, rng.random()))
    for _ in range(rng.randint(1, 4)):
        ivy_bits.append(_tendril(rng, meander, rng.random()))
    ivy_bits.append(
        "".join(_leaves_along(rng, meander, leaf_density))
    )

    rose_bits = _roses(rng, meander, rng.randint(0, 4))

    body = (f'<g opacity="{IVY_OPACITY}">' + "".join(ivy_bits) + "</g>"
            f'<g opacity="{ROSE_OPACITY}">' + "".join(rose_bits) + "</g>")

    wrap = (f'<g transform="translate({TILE_WIDTH:.0f},0) scale(-1,1)">'
            if mirrored else "<g>")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{TILE_WIDTH:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {TILE_WIDTH:.0f} {height:.0f}">'
           f'{_LEAF_DEFS}{wrap}{body}</g></svg>')
    return svg, height


def _cubic_point(p0, p1, p2, p3, t):
    """Point at t on a cubic bezier -- used to hang leaves and offshoots on
    a curve at their true position rather than an approximation."""
    mt = 1 - t
    return (
        mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0],
        mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1],
    )


def _cubic_tangent_deg(p0, p1, p2, p3, t):
    mt = 1 - t
    dx = (3 * mt ** 2 * (p1[0] - p0[0]) + 6 * mt * t * (p2[0] - p1[0])
          + 3 * t ** 2 * (p3[0] - p2[0]))
    dy = (3 * mt ** 2 * (p1[1] - p0[1]) + 6 * mt * t * (p2[1] - p1[1])
          + 3 * t ** 2 * (p3[1] - p2[1]))
    return math.degrees(math.atan2(dy, dx))


@lru_cache(maxsize=64)
def page_vines(page_key: str) -> dict:
    """Everything theme.py needs for one page's background.

    Returns {"left": svg, "left_h": float, "right": svg | None,
    "right_h": float | None}. Some pages get only a left-hand vine -- an
    every-page-identical two-margin frame is itself a kind of regularity,
    and letting roughly a third of pages run sparser keeps the app from
    feeling uniformly decorated.

    Cached because the CSS is rebuilt on every Streamlit rerun, and the
    result is a pure function of the page name.
    """
    both_margins = random.Random(f"{page_key}::layout").random() < 0.65

    left_svg, left_h = build_vine(f"{page_key}::left", mirrored=False)
    result = {"left": left_svg, "left_h": left_h, "right": None, "right_h": None}
    if both_margins:
        right_svg, right_h = build_vine(f"{page_key}::right", mirrored=True)
        result["right"] = right_svg
        result["right_h"] = right_h
    return result
