# PFPA — Financial Data Pipeline

Enter a **company name or ticker**; the pipeline automatically downloads stock
prices, financial statements and interest rates, **aligns them on the stock's
trading calendar**, computes common valuation metrics, and saves everything to
Excel or CSV. Runs on any US-listed company, one at a time or in batch.

## Features

- **One command, any company** — resolve by name or ticker, download & align everything.
- **Point-in-time correct** — fundamentals are joined by SEC *filing date*, so there's
  no look-ahead bias (safe for backtests and event studies).
- **Derived metrics** — TTM revenue/income, market cap, PE, PS, PB, ROE, ROA, net
  margin, current ratio (split-adjusted, so stock splits don't distort market cap).
- **Batch mode** — many companies at once, plus a combined cross-sectional portfolio.
- **Pluggable sources** — each data source is one small function; swap it in one file.
- **Excel or CSV** output; usable as a library (`run_pipeline` / `run_batch`) for any UI.

## Data sources (all official / free)

| Data              | Source                        | Key needed        |
| ----------------- | ----------------------------- | ----------------- |
| Stock prices      | [Tiingo](https://www.tiingo.com) (official) or [yfinance](https://github.com/ranaroussi/yfinance) (fallback) | Tiingo optional; yfinance none |
| Financials        | [SEC EDGAR](https://data.sec.gov) (XBRL company facts) | none (just a UA email) |
| Interest rates    | [FRED](https://fred.stlouisfed.org) (Federal Reserve) | 1 free key |
| Name → symbol     | SEC `company_tickers.json`    | none              |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then edit .env:
#   FRED_API_KEY   -> free key from https://fredaccount.stlouisfed.org/apikeys
#   SEC_USER_AGENT -> "YourProject your_email@example.com"
```

The FRED key is only needed for interest rates; prices and financials work
without any key. If the key is missing the pipeline just skips rates and
continues.

## Usage

Command line:

```bash
python -m pfpa AAPL                              # everything, all history -> output/AAPL.xlsx
python -m pfpa "Apple" --start 2015-01-01        # resolve by name
python -m pfpa MSFT --format csv --out data      # a folder of CSVs instead
python -m pfpa AAPL MSFT NVDA --start 2021-01-01 # batch: also writes output/portfolio.*
python -m pfpa --file tickers.txt                # batch from a file (one per line, # = comment)
python -m pfpa AAPL --no-metrics                 # skip the derived-metric columns
```

From Python (for plugging into a notebook / web app / API):

```python
from pfpa import run_pipeline

result = run_pipeline("NVDA", start="2018-01-01", export=False)  # no files, just data
result.panel          # daily: price + rates + point-in-time fundamentals + metrics
result.prices         # raw daily OHLCV
result.financials     # tidy/long fundamentals (all filings)
result.company        # Company(ticker="NVDA", cik="0001045810", name="NVIDIA CORP")

from pfpa import run_batch
results = run_batch(["AAPL", "MSFT", "NVDA"], start="2021-01-01", export=False)
results["NVDA"].panel  # each company's Result, keyed by ticker
```

## Output

One Excel workbook (or CSV folder) per company with these tables:

- **about** — resolved company identity (ticker, CIK, name)
- **prices** — daily OHLCV, indexed by trading date
- **rates** — interest-rate series, indexed by date
- **financials** — tidy/long fundamentals, every filing (best for custom work)
- **financials_wide** — one row per reporting period end
- **panel** — the aligned daily panel (the main deliverable)

Running several companies at once also writes a combined **`portfolio`** output:
a **summary** (latest metrics, one row per company) and **panel_all** (every
daily panel stacked with a `Symbol` column) — ready for cross-sectional work.

### Derived metrics

With `metrics=True` (default) the panel gains: `Revenue_TTM`, `NetIncome_TTM`,
`MarketCap`, `PE`, `PS`, `PB`, `ROE`, `ROA`, `NetMargin`, `CurrentRatio`.
Two subtleties are handled so the numbers are correct:

- **TTM** — SEC reports no standalone Q4, so it's rebuilt as `FY − (Q1+Q2+Q3)`
  and TTM is a rolling 4-quarter sum, each dated by when its newest quarter was
  *filed*.
- **Market cap** — share counts are put on the same split-adjusted basis as the
  price, so a stock split (e.g. NVIDIA's 10-for-1) doesn't distort the series.

### Point-in-time alignment (no look-ahead bias)

Financials are joined to trading days by their **`filed` date** — the day the
report actually became public — not the period-end date. So each trading day
sees only the fundamentals that were *knowable* on that day. This matters for
backtests and event studies. Interest rates are forward-filled across
non-quoted days (they're step functions).

## Architecture

```
pfpa/
  config.py       # env-driven settings, default FRED series, HTTP headers
  resolve.py      # name/ticker -> {ticker, cik, name}   (SEC ticker map)
  prices.py       # get_prices(ticker)      -> Tiingo / yfinance (+ splits)
  financials.py   # get_financials(cik)     -> SEC EDGAR
  rates.py        # get_rates(series)       -> FRED
  metrics.py      # add_metrics(): TTM + PE/PB/ROE/... ratios
  pipeline.py     # run_pipeline(): orchestrate + align + export
  batch.py        # run_batch(): many companies + combined portfolio output
  cli.py          # argparse front-end
```

Each source is a single plain function returning a `pandas.DataFrame`, so the
providers are the abstraction layer. **To swap a source** (e.g. Alpha Vantage
or a paid terminal for prices), reimplement one function — nothing else
changes. **To add a raw metric**, add an entry to `CONCEPTS` in `financials.py`
or a series to `DEFAULT_FRED_SERIES` in `config.py`; **to add a ratio**, extend
`add_metrics` in `metrics.py`.

## Notes & limits

- Financials & derived metrics cover **US-listed SEC filers**. Non-US companies
  return prices + rates only (the pipeline degrades gracefully).
- yfinance's `Close` is split-adjusted; Tiingo's is raw. Market cap is computed
  split-consistently either way, but keep it in mind if comparing the raw
  `Close` column across backends.
- TTM uses a rolling 4-quarter sum; a company with a missing quarter can produce
  a briefly stale TTM until the next filing.
- The SEC ticker map is cached under `~/.pfpa_cache`.
