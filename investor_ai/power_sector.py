"""Power/AI-infrastructure sector watchlist and book-inspired context.

Inspired by "Power 2026: Electricity Pricing in the Age of AI" (Neel Somani,
power2026.ai), a free educational primer on electricity markets, power
plant economics, and power trading. That book's central thesis: AI
data-center demand is a structural tailwind for efficient natural-gas
generation, grid infrastructure, and the companies that build/operate them.

What this module deliberately does NOT attempt: the book's real trading
math (spark spread, dark spread, locational marginal price, basis trades)
needs live electricity-market data -- ISO price feeds, plant-specific heat
rates, forward power curves -- which has no free equivalent to yfinance and
is normally paid, specialized data (ICE, CME, ISO market operators). The one
piece of that math this module *can* compute with free data is a simplified
proxy: Henry Hub natural gas futures (ticker "NG=F") are freely available
via yfinance, and the book's own spark-spread logic says rising gas prices
squeeze the margins of natural-gas-fired power producers. That's turned
into a single rule-based note below -- not a real spark spread (no power
price or plant heat rate involved), just a directional, inspectable heads-up.

Same philosophy as the rest of this app: fixed rules, not a model, every
number traceable back to a threshold in investor_ai/config.py.
"""

from __future__ import annotations

from investor_ai import config

# Curated, not exhaustive -- a starting watchlist for the "AI power demand"
# theme the book covers, spanning the parts of the supply chain it discusses:
# regulated utilities, merchant/independent power producers, turbine
# manufacturers, natural gas producers, and data-center power/hosting plays.
# `gas_exposed` marks names whose near-term margins plausibly move with
# natural gas prices (per the book's spark-spread logic) -- nuclear-heavy or
# renewables-heavy names are marked False so the gas-margin note doesn't
# misleadingly attach to them.
POWER_SECTOR_WATCHLIST: list[dict] = [
    {"ticker": "NEE", "category": "Regulated Utility", "gas_exposed": False},
    {"ticker": "DUK", "category": "Regulated Utility", "gas_exposed": False},
    {"ticker": "SO", "category": "Regulated Utility", "gas_exposed": False},
    {"ticker": "VST", "category": "Independent Power Producer", "gas_exposed": True},
    {"ticker": "NRG", "category": "Independent Power Producer", "gas_exposed": True},
    {"ticker": "CEG", "category": "Independent Power Producer (nuclear-heavy)", "gas_exposed": False},
    {"ticker": "TLN", "category": "Independent Power Producer (nuclear-heavy)", "gas_exposed": False},
    {"ticker": "GEV", "category": "Turbine Manufacturer", "gas_exposed": False},
    {"ticker": "EQT", "category": "Natural Gas Producer", "gas_exposed": False},
    {"ticker": "WULF", "category": "Data Center Power/Hosting", "gas_exposed": False},
]

# Terms as used in the book, explained in plain English -- same spirit as
# investor_ai/templates.py's glossary for the app's own technical indicators.
BOOK_GLOSSARY: dict[str, str] = {
    "merit_order": (
        "Power plants are ranked cheapest-to-most-expensive by their cost to run. Demand is met "
        "by turning on plants in that order; the last (most expensive) plant needed to meet demand "
        "sets the market price for *everyone*, including cheaper plants."
    ),
    "heat_rate": (
        "How much fuel a power plant burns to produce one unit of electricity -- lower is more "
        "efficient. A modern natural-gas plant might have a heat rate around 6-7; an old coal plant "
        "might be 10 or higher, making it less competitive."
    ),
    "spark_spread": (
        "A natural-gas power plant's rough profit margin: the price it sells power for, minus its "
        "fuel cost (heat rate x natural gas price). When natural gas prices rise faster than power "
        "prices, this margin gets squeezed."
    ),
    "capacity_vs_energy_only": (
        "Some power markets (e.g. PJM, California) pay plants just to exist as backup capacity, on "
        "top of what they earn selling power -- like an insurance policy for the grid. Others (e.g. "
        "Texas/ERCOT, Alberta) pay generators only for power actually delivered, letting prices spike "
        "sharply during shortages instead."
    ),
    "duck_curve": (
        "In grids with lots of solar, daytime power prices can crash toward zero (too much solar "
        "supply), while evening prices spike once the sun goes down and demand is still high -- named "
        "for the shape it makes on a chart of price/demand over the day."
    ),
}


def score_natural_gas_trend(pct_change_month: float | None) -> tuple[str, str | None]:
    """A simplified, book-inspired margin note for natural-gas-exposed power
    producers, based on the trend in free Henry Hub natural gas futures
    (NG=F) over the past ~month.

    This is NOT a real spark spread (that needs an actual power price and a
    specific plant's heat rate) -- just a directional heads-up: rising gas
    prices are a margin headwind for gas-fired generators, falling gas
    prices are a tailwind. Returns (direction, message); direction is one of
    "pressure" / "tailwind" / "neutral"; message is None if the move isn't
    large enough to be notable, or data is unavailable.
    """
    if pct_change_month is None:
        return "neutral", None
    if pct_change_month >= config.NATGAS_MARGIN_PRESSURE_PCT:
        return (
            "pressure",
            f"Henry Hub natural gas is up {pct_change_month:.1f}% over the past month -- per the "
            "book's spark-spread logic, rising fuel costs are a potential margin headwind for "
            "natural-gas-fired power producers.",
        )
    if pct_change_month <= -config.NATGAS_MARGIN_PRESSURE_PCT:
        return (
            "tailwind",
            f"Henry Hub natural gas is down {abs(pct_change_month):.1f}% over the past month -- per "
            "the book's spark-spread logic, falling fuel costs are a potential margin tailwind for "
            "natural-gas-fired power producers.",
        )
    return "neutral", None
