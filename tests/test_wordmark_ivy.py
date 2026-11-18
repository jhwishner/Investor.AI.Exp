"""Tests for the glyph-aware wordmark ivy.

The point of this module is that it MEASURES the type before growing
anything. Every earlier approach scattered vines in a box and hoped they
interacted with the letters; they never could, because nothing in the
generator knew where a glyph was. These tests pin the properties that
depend on that measurement actually happening.
"""

import numpy as np
import pytest

import wordmark_ivy as wm


def test_font_file_is_present_and_readable():
    """The vines are positioned against glyph geometry measured from this
    exact file. If it goes missing the artwork silently misaligns rather
    than failing, so its presence is asserted."""
    assert wm.FONT_PATH.exists(), f"missing font: {wm.FONT_PATH}"
    assert wm._font().getbbox("Ivy") is not None


def test_ink_mask_locates_real_glyphs():
    mask, bbox = wm._ink_mask("Ivy Investments")
    x0, y0, x1, y1 = bbox
    assert mask[y0:y1, x0:x1].any()
    assert mask.sum() > 5000
    # nothing outside the padded bbox
    assert not mask[:y0 - 5].any()


def test_letter_gaps_are_found_between_strokes():
    """Runners thread through these. If gap detection breaks, vines go back
    to lying across the letters."""
    mask, bbox = wm._ink_mask("Ivy Investments")
    gaps = wm._letter_gaps(mask, bbox)
    assert len(gaps) >= 6, f"only {len(gaps)} gaps found"
    assert gaps == sorted(gaps)
    x0, _, x1, _ = bbox
    assert all(x0 <= g <= x1 for g in gaps)


def test_runners_pass_both_behind_and_in_front_of_ink():
    """The weave. A vine that never crosses to the front layer is just
    sitting behind the type; one that never goes back is sitting on top of
    it. Both must occur for the over/under to read as three-dimensional."""
    geo = wm.build(runners=5)
    layers = {s.layer for s in geo.segments}
    assert layers == {"back", "front"}
    front = [s for s in geo.segments if s.layer == "front"]
    assert len(front) >= 5, "too few front crossings to read as woven"


def test_front_segments_actually_sit_on_ink():
    """A front segment exists to cross a letter stroke. If they land on
    blank space the layering is decorative rather than structural."""
    mask, _ = wm._ink_mask("Ivy Investments")
    geo = wm.build(runners=5)
    front = [s for s in geo.segments if s.layer == "front"]
    on_ink = sum(1 for s in front
                 if any(wm._is_ink(mask, x, y) for x, y in s.points))
    assert on_ink / len(front) > 0.8


def test_foliage_is_kept_out_of_dense_ink():
    """Leaves decorate the type; they must not smother it."""
    mask, _ = wm._ink_mask("Ivy Investments")
    geo = wm.build(runners=5)
    buried = sum(1 for lf in geo.leaves if wm._is_ink(mask, lf.x, lf.y, r=8))
    assert buried / len(geo.leaves) < 0.35


def test_geometry_is_deterministic():
    a, b = wm.build(seed="x"), wm.build(seed="x")
    assert [s.points for s in a.segments] == [s.points for s in b.segments]
    assert [(l.x, l.y) for l in a.leaves] == [(l.x, l.y) for l in b.leaves]


def test_leaves_hang_downward():
    """Drooping, not groomed: rotation 0 points the blade straight down."""
    geo = wm.build(runners=5)
    rots = [lf.rot for lf in geo.leaves]
    assert sum(1 for r in rots if abs(r) <= 55) / len(rots) > 0.75
    assert max(abs(r) for r in rots) <= 70.0001


def test_svg_layers_are_well_formed_and_split():
    import xml.etree.ElementTree as ET
    geo = wm.build(runners=5)
    back, front = wm.to_svg(geo, "back"), wm.to_svg(geo, "front")
    for svg in (back, front):
        ET.fromstring(svg)
    assert back != front


def test_rendered_asset_contains_both_ivy_and_type():
    """End-to-end: the composed PNG must actually carry green ivy AND dark
    type. A blank or type-only image would mean the compositing broke."""
    from PIL import Image
    name, aspect = wm.hero_asset("Ivy Investments", runners=5)
    img = Image.open(wm.STATIC_DIR / name).convert("RGBA")
    arr = np.array(img)
    opaque = arr[..., 3] > 200
    assert opaque.sum() > 20_000, "asset is essentially empty"
    rgb = arr[..., :3][opaque].astype(int)
    greenish = ((rgb[:, 1] > rgb[:, 0] + 10) & (rgb[:, 1] > rgb[:, 2] + 5)).sum()
    dark = (rgb.max(axis=1) < 70).sum()
    assert greenish > 3_000, "no ivy in the composed asset"
    assert dark > 3_000, "no type in the composed asset"
    assert 1.5 < aspect < 6.0


def test_asset_is_cached_per_text():
    a = wm.hero_asset("Ivy Investments", runners=5)
    b = wm.hero_asset("Ivy Investments", runners=5)
    assert a is b
    assert wm.hero_asset("Good evening.", seed="greet", runners=2)[0] != a[0]


def test_asset_file_size_is_reasonable():
    """It is fetched once and cached by the browser, but it should not be
    a megabyte."""
    name, _ = wm.hero_asset("Ivy Investments", runners=5)
    assert (wm.STATIC_DIR / name).stat().st_size < 400_000


def test_asset_filename_is_stable_across_processes():
    """Filenames must be content-derived, not builtin-hash derived.

    Python randomises string hashing per process, so a builtin hash() in
    the filename produces a fresh render on every app restart and static/
    grows without bound. Verified by actually spawning a second process.
    """
    import subprocess
    import sys

    here = wm.STATIC_DIR.parent
    got = subprocess.run(
        [sys.executable, "-c",
         "import wordmark_ivy as w; print(w.hero_asset('Ivy Investments', runners=5)[0])"],
        capture_output=True, text=True, cwd=str(here),
    ).stdout.strip()
    assert got == wm.hero_asset("Ivy Investments", runners=5)[0]


def test_pruning_removes_orphans_but_keeps_live_assets():
    live, _ = wm.hero_asset("Ivy Investments", runners=5)
    orphan = wm.STATIC_DIR / "wm-stale-deadbeef00.png"
    orphan.write_bytes(b"\x89PNG\r\n\x1a\n")
    wm._prune_stale_assets({live})
    assert not orphan.exists()
    assert (wm.STATIC_DIR / live).exists()


def test_asset_resolution_covers_retina_at_render_width():
    """The hero renders up to ~1140 CSS px wide. On a 2x display that needs
    ~2280 device px; anything less is upscaled by the browser and looks
    soft. An earlier version shipped 2359px, which went blurry on any
    window wider than ~1180 CSS px.
    """
    from PIL import Image
    name, _ = wm.hero_asset("Good evening, JensenHW.", seed="greet", runners=4, scale=1.45)
    width = Image.open(wm.STATIC_DIR / name).size[0]
    assert width >= 2280 * 1.2, f"{width}px leaves no retina headroom"


def test_supersampling_antialiases_the_vines():
    """PIL draws lines and polygons with no antialiasing. Without the
    supersample+downsample pass every vine edge is stair-stepped, which
    reads as low quality however high the resolution is.

    A downsampled render has many partially-transparent edge pixels; an
    aliased one is almost entirely fully-opaque or fully-clear.
    """
    import numpy as np
    from PIL import Image

    aliased, _ = wm.render_asset("Good evening.", seed="aa-off", runners=3,
                                 scale=1.0, supersample=1, filename="_t_alias.png")
    smooth, _ = wm.render_asset("Good evening.", seed="aa-on", runners=3,
                                scale=1.0, supersample=2, filename="_t_smooth.png")

    def edge_fraction(name):
        a = np.array(Image.open(wm.STATIC_DIR / name).convert("RGBA"))[..., 3]
        drawn = a > 0
        partial = (a > 12) & (a < 243)
        return partial.sum() / max(1, drawn.sum())

    smooth_frac, alias_frac = edge_fraction(smooth), edge_fraction(aliased)
    for f in ("_t_alias.png", "_t_smooth.png"):
        (wm.STATIC_DIR / f).unlink(missing_ok=True)
    assert smooth_frac > alias_frac * 1.5, (
        f"antialiasing not applied (smooth={smooth_frac:.3f} vs aliased={alias_frac:.3f})"
    )
