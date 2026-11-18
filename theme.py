"""Shared visual theme for the app.

Kept at the project root (not in investor_ai/) because it's pure UI styling,
not business logic -- investor_ai/ is reserved for Streamlit-free code.
Called once from app.py (the router), just after st.navigation() resolves
the current page -- apply_theme() needs that page's identity to grow its
background ivy (the artwork itself lives in vines.py, which stays
Streamlit-free so it can be unit-tested).

Design: modern light -- off-white background, soft shadow elevation on
cards instead of heavy borders or glow, a single emerald accent used
sparingly. Navigation lives in a full-width top bar (st.navigation(...,
position="top") in app.py) rather than a sidebar; the account app-bar
below it is its own rounded, shadowed panel in normal document flow (not
pinned/sticky) -- an earlier version tried to zero the gap and pin it to
merge visually with the native nav row, which caused it to render
underneath Streamlit's own (likely position:fixed) header instead. Most of
the palette/typography lives in .streamlit/config.toml (native theming
survives Streamlit upgrades better than CSS); this file adds only what
config.toml can't express: card elevation, button hover lift, the
interactive top-nav links, and the app-bar itself.

NOTE: the header/top-nav-link/bordered-container selectors below
(stHeader, stTopNavLink, stVerticalBlockBorderWrapper) are internal
Streamlit data-testids, not public API -- confirmed against this installed
version's static bundle, but they're the one part of this file that could
go stale on a Streamlit upgrade.
"""

import base64

import streamlit as st

import vines

# Matches config.toml's primaryColor/linkColor/backgroundColor.
_ACCENT = "#047857"
_BG = "#FAFAFA"


# Display face for the home hero only -- an organic, high-contrast serif
# that reads as botanical without tipping into script/novelty. Everything
# else keeps the config.toml faces. MUST be emitted before any rule in the
# stylesheet: browsers ignore an @import that appears after one.
_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2"
    "?family=Cormorant+Garamond:wght@400;500;600;700&display=swap');\n"
)


def _data_uri(svg: str) -> str:
    """Base64 rather than raw/URL-encoded SVG -- the artwork contains #, <,
    and quotes, all of which need escaping inside a CSS url(), and getting
    that wrong fails silently (no background, no error)."""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


# Ivy tangled through the hero type. Two layers per line of text: "back"
# sits behind the letterforms, "front" crosses over them, and the text is
# sandwiched between -- that over/under is what reads as vines growing
# through the words rather than a wreath drawn around them.
#
# Delivered as CSS background-images rather than inline SVG via st.html:
# st.html sanitizes through DOMPurify and an inline attempt produced
# nothing visible on the page. background-image is the path already
# demonstrably working for the page-margin vines.


def _vine_css(page_key: str) -> str:
    """Background rules for one page's procedurally-grown vines.

    Built per page rather than baked in as a constant so every page gets its
    own length, density and wander (see vines.py). Layers are ordered
    left-then-right; a page may legitimately have no right-hand vine.
    """
    data = vines.page_vines(page_key)
    left_uri = _data_uri(data["left"])
    left_h = round(data["left_h"])

    if data["right"] is not None:
        images = f'url("{left_uri}"),\n        url("{_data_uri(data["right"])}")'
        positions = "left top, right top"
        repeats = "repeat-y, repeat-y"
        sizes = f"{vines.TILE_WIDTH:.0f}px {left_h}px, {vines.TILE_WIDTH:.0f}px {round(data['right_h'])}px"
    else:
        images = f'url("{left_uri}")'
        positions = "left top"
        repeats = "repeat-y"
        sizes = f"{vines.TILE_WIDTH:.0f}px {left_h}px"

    return f"""
/* Ivy for this page, grown from its name -- every page differs in length,
   density and wander so the app never reads as one repeated wallpaper.
   Runs down the margins, clear of the content column, so tables and body
   copy stay clean. repeat-y tiles it vertically; the tile is built to join
   seamlessly (see vines.py), so however long the page runs it reads as one
   unbroken vine. */
[data-testid="stAppViewContainer"] {{
    background-image:
        {images};
    background-position: {positions};
    background-repeat: {repeats};
    background-size: {sizes};
}}

/* Narrow viewports: keep only the left vine, and pull it in, so it never
   crowds the content column. */
@media (max-width: 1100px) {{
    [data-testid="stAppViewContainer"] {{
        background-image: url("{left_uri}");
        background-position: left top;
        background-repeat: repeat-y;
        background-size: 170px {left_h}px;
    }}
}}
"""


_CSS = f"""
/* Native top-nav's chrome region -- same background as the app-bar below
   it, so the two rows read as one family rather than clashing colors.
   NOT attempting to close the gap between them or pin the app-bar with
   position:sticky anymore -- that combination is what caused it to render
   underneath/behind the native header (which is very likely position:fixed,
   meaning the page's default top padding exists specifically to keep
   content from going under it -- removing that padding, which I did in an
   earlier pass, was the actual bug, not font sizing). Accepting a small
   natural gap here in exchange for not overlapping Streamlit's own chrome. */
[data-testid="stHeader"] {{
    background-color: {_BG};
}}

/* Account control (see auth_ui._render_account_control): pinned to the
   top-right so it sits on the same horizontal axis as the native top nav,
   which Streamlit renders in its own header region that page content
   cannot be placed inside. Fixed positioning is the only way to reach that
   axis from the content area.

   `right` clears Streamlit's own toolbar (the overflow menu still renders
   there even with client.toolbarMode="minimal"); the z-index sits above
   the header's own stacking context. Targeted via its explicit key= --
   .st-key-account_bar -- a documented Streamlit convention, not a guessed
   internal selector.

   Caveat worth knowing when adjusting: `position: fixed` resolves against
   the viewport UNLESS an ancestor establishes a containing block (a
   transform/filter/will-change). If this ever detaches and starts
   scrolling with the page, that's the cause. */
.st-key-account_bar {{
    position: fixed;
    top: 0.55rem;
    right: 3.75rem;
    z-index: 1000000;
    width: auto !important;
    align-items: center;
    gap: 0.5rem;
}}
.st-key-account_bar [data-testid="stCaptionContainer"] {{
    white-space: nowrap;
    margin: 0;
}}
.st-key-account_bar .stButton > button {{
    padding: 0.25rem 0.75rem;
}}

/* Narrow screens: the nav needs the room more than the greeting does. */
@media (max-width: 900px) {{
    .st-key-account_bar [data-testid="stCaptionContainer"] {{
        display: none;
    }}
    .st-key-account_bar {{
        right: 3.25rem;
    }}
}}

/* --- Home hero: a threshold, not a header ----------------------------- */
/* The hero owns the whole first screen so the dashboard is something you
   arrive at rather than something already there. min-height is on the
   container Streamlit already lays out as a flex column, so only the
   centring needs declaring -- redeclaring `display` here would fight its
   own layout. */
.st-key-ivy_hero {{
    min-height: 84vh;
    justify-content: center;
    align-items: center;
    position: relative;
    background-image:
        radial-gradient(ellipse 58% 40% at 50% 46%,
                        rgba(4, 120, 87, 0.09) 0%,
                        rgba(4, 120, 87, 0.035) 44%,
                        rgba(250, 250, 250, 0) 74%);
    background-repeat: no-repeat;
    background-position: center 46%;
    background-size: 100% 100%;
}}

/* Site name, top-left, the way a masthead sits on most sites. Plain text
   rather than another rendered asset: it is small, so the ivy treatment
   would be illegible, and it saves a second image on every page. */
.st-key-ivy_brand h1 {{
    font-family: 'Cormorant Garamond', Georgia, serif !important;
    font-size: 1.45rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em;
    text-align: left;
    margin: 0 0 0 0.15rem !important;
    padding: 0 !important;
    line-height: 1.3 !important;
    opacity: 0.9;
}}

/* The greeting is the hero now -- the ivy-woven asset. */
.st-key-ivy_greeting img {{
    max-width: min(1140px, 95vw);
    margin: 0 auto;
    display: block;
}}

/* Wordmark repeated beneath the greeting, quieter than it. */
.ivy-sub {{
    font-family: 'Cormorant Garamond', Georgia, serif !important;
    font-size: 1.6rem !important;
    font-weight: 500;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    text-align: center;
    opacity: 0.55;
    margin: 0.4rem 0 0 !important;
}}

/* The real <h1> stays in the document for screen readers and semantics,
   since the visible wordmark is an image. */
.sr-only {{
    position: absolute !important;
    width: 1px; height: 1px;
    padding: 0; margin: -1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
    border: 0;
}}


/* Scroll cue at the foot of the threshold. */
.st-key-ivy_scrollcue p {{
    text-align: center;
    font-size: 0.72rem !important;
    letter-spacing: 0.26em;
    text-transform: uppercase;
    opacity: 0.5;
}}
.st-key-ivy_scrollcue {{
    margin-top: 3.5rem;
}}

@media (max-width: 700px) {{
    .st-key-ivy_hero {{ min-height: 72vh; background-size: 100% 100%, 150% auto; }}
}}

/* --- Scroll behaviour -------------------------------------------------
   Scroll-driven CSS animations: the hero fades as it leaves, and each data
   section rises in as it enters.

   Wrapped in @supports deliberately. `animation: ... both` holds the
   from-state when a timeline doesn't resolve, so in a browser without
   scroll-driven animation support these rules would leave the dashboard
   stuck at opacity 0 -- content invisible, no error. Gating on support
   means the fallback is simply "no animation, everything visible".
   Also gated on prefers-reduced-motion. */
/* Arrival: the threshold resolves into view on load. Time-based, and it
   ENDS at the visible state, so it is safe everywhere -- no @supports gate
   needed. Only reduced-motion opts out. */
@media (prefers-reduced-motion: no-preference) {{
    @keyframes ivy-portal-open {{
        from {{ opacity: 0; transform: scale(0.955); }}
        to   {{ opacity: 1; transform: scale(1); }}
    }}
    @keyframes ivy-greet {{
        from {{ opacity: 0; transform: translateY(0.9rem); }}
    }}
    @keyframes ivy-cue-bob {{
        0%, 100% {{ transform: translateY(0); opacity: 0.45; }}
        50%      {{ transform: translateY(0.4rem); opacity: 0.8; }}
    }}

    .st-key-ivy_title {{
        animation: ivy-portal-open 1.5s cubic-bezier(0.22, 0.61, 0.36, 1) both;
    }}
    .st-key-ivy_greeting {{
        animation: ivy-greet 1.2s ease-out 0.75s both;
    }}
    .st-key-ivy_scrollcue {{
        animation: ivy-cue-bob 2.6s ease-in-out 2s infinite;
    }}
}}

/* Passing through: on scroll the threshold scales up past the viewer and
   dissolves, and the dashboard rises through behind it.

   Wrapped in @supports deliberately. `animation: ... both` holds the
   from-state when a timeline doesn't resolve, so without scroll-driven
   animation support these rules would leave the dashboard stuck at
   opacity 0 -- content invisible, no error. Gating on support means the
   fallback is simply "no animation, everything visible". */
@supports (animation-timeline: view()) {{
    @media (prefers-reduced-motion: no-preference) {{
        @keyframes ivy-portal-through {{
            to {{ opacity: 0; transform: scale(1.18); }}
        }}
        @keyframes ivy-rise-in {{
            from {{ opacity: 0; transform: translateY(2.5rem); }}
        }}

        .st-key-ivy_hero {{
            animation: ivy-portal-through linear both;
            animation-timeline: view();
            animation-range: exit 0% exit 90%;
        }}

        [class*="st-key-reveal_"] {{
            animation: ivy-rise-in ease-out both;
            animation-timeline: view();
            animation-range: entry 5% entry 70%;
        }}
    }}
}}

/* --- Interactive top nav -- larger text, hover lift, active underline --- */
[data-testid="stTopNavLink"] {{
    border-radius: 8px;
    font-size: 1.05rem;
    transition: background-color 0.15s ease, transform 0.15s ease;
}}
[data-testid="stTopNavLink"]:hover {{
    background-color: rgba(4, 120, 87, 0.08);
    transform: translateY(-1px);
}}
[data-testid="stTopNavLink"][aria-current="page"] {{
    background-color: rgba(4, 120, 87, 0.1);
    font-weight: 600;
    box-shadow: inset 0 -2px 0 {_ACCENT};
}}

/* Soft shadow elevation on metric "cards" -- modern flat-SaaS convention */
[data-testid="stMetric"] {{
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
}}

/* Bordered containers (position cards on Recommendations / Power pages) */
[data-testid="stVerticalBlockBorderWrapper"] {{
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
}}

/* Buttons: a slight lift on hover instead of a flat color swap */
.stButton > button, .stFormSubmitButton > button {{
    transition: box-shadow 0.15s ease, transform 0.1s ease;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover {{
    box-shadow: 0 2px 8px rgba(4, 120, 87, 0.25);
    transform: translateY(-1px);
}}
"""


def apply_theme(page_key: str = "home") -> None:
    """Inject the CSS config.toml can't express, including this page's vines.

    `page_key` seeds the vine generator, so it must be stable for a given
    page (Streamlit's page url_path is ideal) -- pass the same value on
    every rerun or the artwork will change under the user. Called from
    app.py after st.navigation() returns, which is where the current page
    becomes known.
    """
    st.markdown(
        "<style>" + _FONT_IMPORT + _vine_css(page_key) + _CSS + "</style>",
        unsafe_allow_html=True,
    )
