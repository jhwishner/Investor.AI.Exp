"""Plain-English glossary used both by rule commentary and standalone
"What does this mean?" UI expanders.

Keeping wording here (separate from the condition/threshold logic in
rules.py) means either can be edited without touching the other.
"""

EXPLANATIONS: dict[str, str] = {
    "rsi": (
        "**RSI (Relative Strength Index)** measures how fast and how far a price has moved "
        "recently, on a 0-100 scale. Above 70 is conventionally called 'overbought' (it's risen "
        "quickly and may be due for a pause or pullback); below 30 is 'oversold' (it's fallen "
        "quickly and may be due for a bounce). It's a short-term gauge, not a prediction."
    ),
    "sma": (
        "A **Simple Moving Average (SMA)** is the average closing price over the last N days. "
        "It smooths out day-to-day noise so you can see the underlying trend. Price above its "
        "SMA generally suggests an uptrend; price below suggests a downtrend."
    ),
    "sma_crossover": (
        "When a **shorter-term moving average crosses above a longer-term one** (e.g. the 50-day "
        "crossing above the 200-day, sometimes called a 'golden cross'), it's a classic signal "
        "that a longer-term uptrend may be forming. The reverse ('death cross') suggests the "
        "opposite. These are lagging signals -- they confirm a trend after it's underway, not before."
    ),
    "macd": (
        "**MACD (Moving Average Convergence Divergence)** compares a fast and slow moving average "
        "to gauge trend momentum. When the MACD line crosses above its signal line, momentum is "
        "shifting bullish; crossing below suggests momentum shifting bearish. The histogram shows "
        "the gap between the two -- growing bars mean the trend is strengthening."
    ),
    "bollinger": (
        "**Bollinger Bands** plot a band around the moving average based on recent volatility. "
        "Price pushing above the upper band or below the lower band signals an unusually strong "
        "move relative to its recent range -- it doesn't necessarily mean 'reverse now', just "
        "that the move is statistically stretched."
    ),
    "volatility": (
        "**Historical volatility** measures how much a price has swung around recently, "
        "expressed as an annualized percentage. Higher volatility means bigger, faster price "
        "swings (more risk, in both directions) -- broad stock market indices typically run "
        "around 15-20% annualized; individual stocks are often higher."
    ),
    "momentum": (
        "**Momentum** is simply the percent change in price over a given window. Positive "
        "momentum means the price has been rising over that period; negative means it's been "
        "falling. It says nothing about whether that will continue."
    ),
    "volume": (
        "**Trading volume** is how many shares changed hands. Volume well above its recent "
        "average (a 'volume spike') often accompanies news or a shift in investor sentiment, "
        "and can make a price move more credible than the same move on light volume."
    ),
    "fifty_two_week": (
        "The **52-week range** is the highest and lowest price over roughly the past year. "
        "Where a stock currently sits in that range is a rough gauge of near-term investor "
        "sentiment -- near the high suggests strength, near the low suggests weakness -- but "
        "says nothing on its own about whether the price is cheap or expensive."
    ),
    "pe_ratio": (
        "The **P/E (price-to-earnings) ratio** is the share price divided by annual earnings per "
        "share. It's a rough measure of how expensive a stock is relative to its profits -- a "
        "higher P/E can mean investors expect faster future growth, or it can mean the stock is "
        "simply overvalued. It's only meaningful compared against similar companies or the "
        "company's own history; it isn't computable for unprofitable companies."
    ),
    "dividend_yield": (
        "**Dividend yield** is the annual dividend payment divided by the share price, showing "
        "roughly how much cash income the stock pays relative to its cost. Not all companies pay "
        "dividends -- a missing value usually just means the company reinvests profits instead."
    ),
    "beta": (
        "**Beta** measures how much a stock tends to move relative to the overall market. A beta "
        "of 1.0 means it tends to move in line with the market; above 1.0 means bigger swings "
        "than the market (higher risk/reward); below 1.0 means smaller swings."
    ),
}
