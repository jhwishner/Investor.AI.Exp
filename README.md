# Ivy Investments -- Personal Market Analyst (Paper Trading, No AI API)

A local, free, paper-trading research tool. It fetches market data, computes
standard quantitative signals (moving averages, RSI, MACD, Bollinger Bands,
volatility, valuation ratios), and turns those into plain-English commentary
using **fixed rules -- not an AI model**. No API keys, no subscriptions, no
external accounts. Everything runs on your own computer.

**This is not financial advice.** It's an educational tool for tracking a
hypothetical ("paper") portfolio and learning what common quant signals mean.

---

## One-time setup (macOS)

### Step 0: Install Xcode Command Line Tools (required, one-time only)

Open **Terminal** (Cmd+Space, type "Terminal", press Enter) and run:

```bash
python3 --version
```

If a dialog pops up asking "Install Command Line Developer Tools?", click
**Install**, accept the license if prompted, and wait for it to finish (this
can take several minutes -- it's a one-time download from Apple). Once it's
done, run `python3 --version` again to confirm it now prints a version
number like `Python 3.9.6`.

You only need to do this once, ever, on this machine.

### Step 1: Set up the project

In Terminal:

```bash
cd /Users/JensenHW/Investor.AI.Exp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

This creates an isolated Python environment (`venv/`) and installs the
libraries this app needs (streamlit, yfinance, pandas, numpy, the
auto-refresh helper) plus pytest for the test suite. It won't affect
anything else on your computer.

### Step 2: Run it

```bash
streamlit run app.py
```

Your browser should open automatically to `http://localhost:8501`. If it
doesn't, copy that address into your browser manually.

The first thing you'll see is a **log in / create account** screen -- see
"Accounts" below. Create one to get started; if you already had paper trades
logged before accounts existed, they're automatically assigned to the very
first account created (see "Accounts" for the details).

To stop the app, go back to Terminal and press `Ctrl+C`.

### Running it again later

You don't need to repeat Step 1. Just:

```bash
cd /Users/JensenHW/Investor.AI.Exp
source venv/bin/activate
streamlit run app.py
```

---

## What's in each page (left sidebar)

- **Home** -- what this tool does, plus a portfolio snapshot.
- **Ticker Analysis** -- look up any stock ticker and see Day / Week / Month /
  Year signals, charts, and plain-English commentary with "What does this
  mean?" explanations. Also includes, each in its own expandable section:
  recent **news headlines with rule-based bullish/bearish/neutral tagging**
  (keyword matching, not AI -- see "What does this mean?" inside that
  section), **annual financial statements** (income statement, balance
  sheet, cash flow), **earnings history**, and **ownership data** (insider
  transactions, institutional holders). All free, no API key -- see "Free
  data sources" below for what's unavailable on ETFs/funds.
- **Market Movers** -- a market-wide (not portfolio-specific) snapshot of
  today's Top Gainers, Top Losers, and Most Active tickers.
- **Power & AI Infrastructure** -- a curated watchlist (utilities, independent
  power producers, turbine manufacturers, natural gas producers, data-center
  power/hosting plays) inspired by the free educational primer *"Power 2026:
  Electricity Pricing in the Age of AI"* (Neel Somani), plus a natural-gas
  price trend note and a glossary of the book's key terms (merit order, heat
  rate, spark spread, capacity vs. energy-only markets, duck curve). See
  "Where the Recommendations logic comes from" below for exactly what is (and
  isn't) implemented from that book, and why.
- **Manage Positions** -- log a hypothetical BUY or SELL (this does **not**
  place a real trade anywhere -- it's just recorded in your local database).
  Each trade is tagged with an **account** (e.g. "Roth IRA", "Robinhood",
  "401k") -- pick an existing one from the dropdown or type a new name; if
  you leave it blank, it goes into a default "General" account. You can also
  **import real trades from Fidelity**: Fidelity has no public API for
  personal apps to connect to, so this works by uploading the transaction
  history CSV you export from fidelity.com (Accounts & Trade > Activity &
  Orders > Export) -- only actual buy/sell rows are imported, and
  re-uploading an overlapping export is safe since already-logged rows are
  skipped. See `investor_ai/fidelity_import.py`.
- **Portfolio** -- an "All accounts combined" total, plus a separate
  subsection per account you've used, each with its own open positions,
  unrealized profit/loss, and Day/Week/Month/Year performance breakdown.
- **Recommendations** -- rule-based BUY/SELL/HOLD suggestions (and suggested
  size) for each current position, split into **Long-Term Holdings (Funds &
  ETFs)** -- which also get a multi-year comparison against the S&P 500 -- and
  **Individual Stocks**, which are evaluated on Day/Week/Month/Year signals only.
  Also includes an **Ideal Portfolio Screener** at the bottom: scores your
  current holdings *plus* whatever's currently in Market Movers using the same
  trend/momentum rules plus a Fama-French-inspired size/book-to-market factor
  score -- surfacing candidates you don't currently own. See "Where the
  Recommendations logic comes from" below for what that is (and isn't) based on.

## Accounts (logins)

Every person who uses this app creates their own username/password account,
and each account has a completely separate, private paper portfolio -- your
positions are never visible to anyone else's account, and theirs are never
visible to yours.

*(This is different from the "account" dropdown on Manage Positions/Portfolio
-- that's just a label you choose, like "Roth IRA" or "Robinhood", to group
your own trades within your own login. It has no password and isn't visible
to anyone else either way.)*

- **No external sign-in** (no "Sign in with Google") -- usernames and
  passwords are stored locally in this app's own database. Passwords are
  hashed (never stored in plain text).
- **Staying logged in only lasts for your current browser session.** Closing
  the tab, restarting your browser, or restarting the app itself will ask
  you to log in again -- there's no "remember me" yet.
- **If you had paper trades logged before accounts existed** (from before
  this feature was added), they weren't lost: the very first account anyone
  creates on this database automatically inherits all of that old data. Every
  account created after that first one starts with a clean, empty portfolio.
- This is a good fit for sharing the app with a few people you trust on your
  own network or a small private deployment. It is **not** hardened for a
  large public deployment (e.g., there's no password-reset flow, no rate
  limiting on login attempts, no email verification).

## Your data

Everything is stored in a single file: `data/portfolio.db` (accounts and
everyone's transactions together, kept separate internally by account). To
back it up, just copy that file somewhere safe. To start over completely,
delete it (the app will recreate an empty one, with no accounts, next time
it runs).

## Free data sources (no API key, ever)

News, financial statements, earnings history, insider transactions,
institutional holders, and Market Movers are all fetched through the same
free `yfinance` library already used for prices -- **no API key was added
to this app, and none is needed.** Two caveats specific to these newer
features:

- **News headlines and Market Movers use an unofficial, undocumented Yahoo
  Finance endpoint** (the same one Yahoo's own website calls) rather than a
  stable published API. It can go empty or change shape without warning if
  Yahoo changes something on their end -- if that happens, the affected
  section will just show "couldn't fetch" rather than breaking the page.
- **Financial statements, earnings history, and ownership data are usually
  unavailable for ETFs/mutual funds/indices** (e.g. VOO) since those don't
  file the same reports individual companies do -- that section will say so
  plainly rather than showing empty tables.
- **Headline sentiment is simple keyword matching** (see
  `investor_ai/sentiment.py`), not AI -- consistent with the rest of this
  app, it's a fixed, inspectable word list, not a model's judgment call.

## Where the Recommendations logic comes from

The rule-based signals throughout this app (RSI, moving averages, MACD,
Bollinger Bands) are standard technical-analysis indicators. The **Ideal
Portfolio Screener**'s factor score (`investor_ai/factor_model.py`) is
explicitly modeled on Fama & French's 1992 paper *"The Cross-Section of
Expected Stock Returns"*, which found that a company's size (market cap)
and book-to-market ratio historically explained average stock returns
better than market beta did. This app applies that as simple size/value
buckets to one stock at a time -- not the original paper's NYSE-decile
breakpoints, which need the full market's data each period to compute.

Two other trading-strategy papers were deliberately **not** built into this
app, on request, because they don't fit its design:

- A neural-network (BiLSTM) price predictor was left out because it's a
  black-box model -- it would break this app's core rule (every number
  shown is traceable back to a fixed, readable threshold, never a trained
  model's internal judgment).
- An institutional portfolio-execution-cost paper (minimizing market impact
  when liquidating large positions) was left out because it solves a
  problem retail-sized paper trades don't actually have -- there's no
  market impact to manage at this scale.

The **Power & AI Infrastructure** page is inspired by a fourth, different
kind of source: *"Power 2026: Electricity Pricing in the Age of AI"* (Neel
Somani, power2026.ai), a free educational primer on electricity markets --
not an academic paper. Its core quantitative tools (spark spread, locational
marginal price, basis trades) all need live electricity-market data --
plant-specific heat rates, forward power curves, ISO price feeds -- which
has no free equivalent to yfinance and is normally paid, specialized data.
The one piece of that math implemented here is a simplified proxy: free
Henry Hub natural gas futures (`NG=F` via yfinance) as a directional,
rule-based margin note for natural-gas-exposed power producers -- not a real
spark spread, since that also needs an actual power price and a specific
plant's heat rate. See `investor_ai/power_sector.py` for the full reasoning.

## Known limitations (by design)

- **Data is free (Yahoo Finance via `yfinance`) and may be end-of-day or
  briefly delayed.** This is a research tool, not a real-time trading
  terminal -- always double check anything important before acting on it.
- **Cost basis is weighted-average**, not FIFO/LIFO tax lots -- fine for
  tracking, not for tax reporting.
- **The Day/Week/Month/Year portfolio performance breakdown is an
  approximation**: it assumes your currently-held share counts were constant
  across each lookback window, rather than replaying your full transaction
  history day by day. If you bought a position partway through a window,
  that window's "change" figure will be a rough estimate, not exact.
- **No AI/LLM is used anywhere.** All commentary comes from fixed rules and
  thresholds (see `investor_ai/rules.py` and `investor_ai/templates.py`) --
  the wording is always traceable back to the specific rule that produced it.
- **Fund vs. stock classification is automatic**, based on Yahoo Finance's
  own `quoteType` field (ETF/mutual fund/index vs. equity) -- an
  unrecognized type defaults to the Individual Stocks section.
- **The benchmark comparison uses SPY (S&P 500) and aligns to whatever
  history the fund actually has** -- a fund that IPO'd 2 years ago is
  compared against the benchmark's matching 2-year window, not a full 5
  years, so the "annualized" figures are always apples-to-apples.
- **Accounts are basic by design** -- self-contained username/password only,
  session-only login (no "remember me"), no password reset, no rate
  limiting on login attempts. Fine for a small trusted group; not a
  hardened multi-tenant auth system.

## Running the automated tests (optional, but recommended)

With the virtual environment active (`source venv/bin/activate`):

```bash
pytest
```

These tests cover the indicator math (`investor_ai/indicators.py`), the
portfolio ledger and P&L calculations (`investor_ai/portfolio.py`), the rule
engine (`investor_ai/rules.py`), the recommendation scoring
(`investor_ai/recommendations.py`), the fund/stock classifier
(`investor_ai/data.py`), the benchmark comparison math
(`investor_ai/benchmarks.py`), the account system (`investor_ai/auth.py`,
including that accounts truly can't see each other's data), the
headline sentiment scorer (`investor_ai/sentiment.py`), the
Fama-French-inspired factor scoring (`investor_ai/factor_model.py`), and the
power/AI-infrastructure sector module (`investor_ai/power_sector.py`) -- all
without touching the network or your real portfolio database.

## Project structure (for future reference / extending)

```
app.py                        # Home page
auth_ui.py                    # Login/signup/logout UI, shared across every page
theme.py                      # Shared visual theme (fonts, colors, card styling)
live.py                       # Shared auto-refresh + "last checked" footer
.streamlit/config.toml        # Streamlit's native theme config
pages/1_Portfolio.py          # Portfolio overview
pages/2_Ticker_Analysis.py    # Day/Week/Month/Year ticker analysis
pages/3_Manage_Positions.py   # Log paper trades
pages/4_Recommendations.py    # BUY/SELL/HOLD suggestions, split fund vs. stock
pages/5_Market_Movers.py      # Market-wide top gainers/losers/most active
pages/6_Power_and_AI_Infrastructure.py  # Power/AI-infra sector watchlist + book glossary
investor_ai/                  # Pure-Python core logic (no Streamlit here)
  config.py                   # Paths, cache lifetimes, rule thresholds
  db.py                       # Shared SQLite connection helper
  data.py                     # yfinance fetch, caching, error handling, fund/stock classifier
  indicators.py               # SMA, EMA, RSI, MACD, Bollinger, volatility, etc.
  signals.py                  # Combines data + indicators into per-timeframe signal dicts
  rules.py                    # Rule-based commentary engine
  templates.py                # Plain-English glossary/explanations
  sentiment.py                 # Rule-based keyword sentiment scoring for news headlines
  auth.py                      # Username/password accounts (hashing, create/authenticate)
  portfolio.py                 # SQLite transaction ledger + P&L math, scoped per account
  recommendations.py           # BUY/SELL/HOLD scoring built on top of rules.py
  factor_model.py               # Fama-French-inspired size/book-to-market factor scoring
  power_sector.py               # Power/AI-infra watchlist, book glossary, nat-gas margin note
  benchmarks.py                # Long-term fund/ETF vs. S&P 500 comparison math
tests/                        # pytest tests for the logic above
data/portfolio.db             # Accounts + everyone's paper portfolios (created on first run)
```
