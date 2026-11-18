"""Tests for the procedural background vine generator.

The important one is seam continuity: the artwork tiles vertically, so if
the centerline's position or slope differs between t=0 and t=1 the repeat
shows a visible step or kink. That property comes from using only
whole-number sine frequencies, and it's checked here across many seeds
rather than trusted.
"""

import math
import random
import re
import xml.etree.ElementTree as ET

import pytest

import vines

SEEDS = [f"page-{i}" for i in range(60)]


@pytest.mark.parametrize("seed", SEEDS)
def test_meander_is_seamless_in_position_and_slope(seed):
    rng = random.Random(seed)
    m = vines._Meander(rng, height=1200, max_amp=60, center=90)
    assert m.x(0.0) == pytest.approx(m.x(1.0), abs=1e-9)
    assert m.dx(0.0) == pytest.approx(m.dx(1.0), abs=1e-9)


@pytest.mark.parametrize("seed", SEEDS)
def test_meander_uses_only_integer_frequencies(seed):
    # This is the underlying reason the seam works; if a fractional
    # frequency ever sneaks in, the continuity test above could still pass
    # by luck for some phases but fail for others.
    rng = random.Random(seed)
    m = vines._Meander(rng, height=1200, max_amp=60, center=90)
    for _amp, freq, _phase in m.terms:
        assert freq == int(freq)


@pytest.mark.parametrize("seed", SEEDS)
def test_meander_stays_inside_the_tile(seed):
    """Amplitude normalization must keep the line off the tile edges, or
    the vine would clip against the neighbouring tile."""
    rng = random.Random(seed)
    center, max_amp = 90, 60
    m = vines._Meander(rng, height=1200, max_amp=max_amp, center=center)
    xs = [m.x(i / 400) for i in range(401)]
    assert min(xs) >= center - max_amp - 1e-6
    assert max(xs) <= center + max_amp + 1e-6
    assert min(xs) > 0
    assert max(xs) < vines.TILE_WIDTH


@pytest.mark.parametrize("seed", SEEDS[:20])
def test_generated_svg_is_well_formed(seed):
    svg, _height = vines.build_vine(seed)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.get("viewBox") is not None


def test_build_vine_returns_matching_height_and_viewbox():
    svg, height = vines.build_vine("some-page")
    root = ET.fromstring(svg)
    _, _, _w, h = root.get("viewBox").split()
    # The CSS background-size uses the returned height, so a mismatch here
    # would stretch or squash the artwork.
    assert float(h) == pytest.approx(height, abs=1.0)
    assert float(root.get("height")) == pytest.approx(height, abs=1.0)


def test_same_page_is_stable_across_calls():
    """A vine that reshuffled on every rerun would be distracting."""
    a, ha = vines.build_vine("portfolio::left")
    b, hb = vines.build_vine("portfolio::left")
    assert a == b
    assert ha == hb


def test_different_pages_get_different_vines():
    seen = {vines.build_vine(f"{name}::left")[0]
            for name in ("home", "portfolio", "movers", "recs", "power")}
    assert len(seen) == 5


def test_mirrored_vine_differs_from_unmirrored():
    plain, _ = vines.build_vine("x", mirrored=False)
    mirrored, _ = vines.build_vine("x", mirrored=True)
    assert "scale(-1,1)" in mirrored
    assert "scale(-1,1)" not in plain


def test_page_vines_shape():
    data = vines.page_vines("home")
    assert data["left"].startswith("<svg")
    assert data["left_h"] > 0
    # right margin is optional by design
    if data["right"] is not None:
        assert data["right"].startswith("<svg")
        assert data["right_h"] > 0


def test_page_vines_is_cached_and_stable():
    assert vines.page_vines("recommendations") is vines.page_vines("recommendations")


def test_some_pages_run_single_margin_and_some_double():
    """The variation the feature exists for -- if every page came out the
    same, the artwork would be uniform again."""
    layouts = {vines.page_vines(f"p{i}")["right"] is None for i in range(40)}
    assert layouts == {True, False}


def test_vine_geometry_varies_between_pages():
    heights = {round(vines.page_vines(f"p{i}")["left_h"]) for i in range(25)}
    assert len(heights) > 15  # repeat length genuinely differs page to page


def test_opacities_match_the_approved_faded_strength():
    svg, _ = vines.build_vine("home::left")
    assert f'opacity="{vines.IVY_OPACITY}"' in svg
    assert f'opacity="{vines.ROSE_OPACITY}"' in svg


@pytest.mark.parametrize("seed", SEEDS[:15])
def test_path_data_contains_no_nan_or_inf(seed):
    svg, _ = vines.build_vine(seed)
    lowered = svg.lower()
    assert "nan" not in lowered
    assert "inf" not in lowered


def test_tangent_is_finite_everywhere():
    m = vines._Meander(random.Random("t"), height=1200, max_amp=60, center=90)
    for i in range(200):
        assert math.isfinite(m.tangent_deg(i / 200))


# --- leaf construction ------------------------------------------------------


_SVG_NS = "{http://www.w3.org/2000/svg}"


def _leaf_groups(svg: str) -> int:
    return svg.count('<use href="#iv"')


def _leaf_rotations(svg: str) -> list[float]:
    """Rotations of LEAF groups only.

    Deliberately parsed rather than regexed off the raw string: blooms and
    buds carry a rotate() too (a full 0-360 spin), so a pattern match over
    the document mixes their angles in and makes any claim about how the
    foliage sits meaningless. A leaf group is identified by holding a
    <use href="#iv">.
    """
    out: list[float] = []
    for group in ET.fromstring(svg).iter(f"{_SVG_NS}g"):
        if not group.findall(f"{_SVG_NS}use"):
            continue
        match = re.search(r"rotate\((-?[\d.]+)\)", group.get("transform") or "")
        if match:
            out.append(float(match.group(1)))
    return out


@pytest.mark.parametrize("seed", SEEDS[:12])
def test_every_leaf_is_attached_by_a_petiole(seed):
    """Each leaf blade must ship with a stalk joining it to the vine.

    Without one the blade sits at a bare point on the curve and reads as a
    sticker placed near the vine rather than growing out of it -- the
    'disconnected' look this replaced.

    Checked structurally rather than by counting substrings: offshoot
    branches also begin "M0,0", so a naive count conflates them with
    stalks. Walking the tree asserts the real invariant -- every group
    holding a blade also holds that blade's own stalk.
    """
    for svg in (vines.build_vine(seed)[0], vines.build_vine(seed, mirrored=True)[0]):
        root = ET.fromstring(svg)
        blades = 0
        for group in root.iter(f"{_SVG_NS}g"):
            uses = group.findall(f"{_SVG_NS}use")     # direct children only
            if not uses:
                continue
            assert len(uses) == 1, "a leaf group holds exactly one blade"
            stalks = [pt for pt in group.findall(f"{_SVG_NS}path")
                      if (pt.get("d") or "").startswith("M0,0")]
            assert stalks, "blade has no petiole joining it to the vine"
            blades += 1
        assert blades > 0


def test_leaf_outline_is_lobed_not_a_teardrop():
    """A real ivy leaf is palmately lobed. The silhouette is what makes it
    read as ivy rather than as a generic leaf, so the lobe structure is
    pinned here."""
    assert vines._LEAF.count("C") == 10
    assert vines._LEAF.strip().endswith("Z")


def test_leaf_geometry_is_defined_once_per_document():
    """The outline is ~200 chars and appears 90+ times; storing it once and
    referencing it keeps the injected CSS (re-sent on every Streamlit
    rerun) from ballooning."""
    for svg in (vines.build_vine("q")[0], vines.build_vine("x")[0]):
        assert svg.count("<defs>") == 1
        assert svg.count('id="iv"') == 1
        assert _leaf_groups(svg) > 5
        assert vines._LEAF not in svg.split("</defs>")[1]  # never repeated inline


def test_foliage_uses_more_than_one_shade():
    svg = vines.build_vine("q")[0]
    assert sum(shade in svg for shade in vines._LEAF_SHADES) >= 2
