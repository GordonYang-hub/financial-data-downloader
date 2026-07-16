"""End-to-end pipeline: resolve -> download -> align on trading dates -> export.

The public entry point is :func:`run_pipeline`. It returns a :class:`Result`
holding every intermediate DataFrame, so an interface (web app, notebook, API)
can consume the data directly without touching disk (pass ``export=False``).
"""
from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from .financials import get_financials
from .metrics import add_metrics
from .prices import get_prices, resolve_source, split_adjust_shares
from .rates import get_rates
from .resolve import Company, resolve


@dataclass
class Result:
    """Everything the pipeline produced for one company."""

    company: Company
    prices: pd.DataFrame          # daily OHLCV, indexed by trading Date
    rates: pd.DataFrame           # interest-rate series, indexed by Date
    financials: pd.DataFrame      # tidy/long fundamentals
    financials_wide: pd.DataFrame  # fundamentals, one row per PeriodEnd
    panel: pd.DataFrame           # daily panel aligned on trading dates
    files: list = field(default_factory=list)


def _asof_join(panel: pd.DataFrame, right: pd.DataFrame, on: str) -> pd.DataFrame:
    """As-of merge ``right`` (sorted by ``on``) onto ``panel``'s trading dates,
    attaching each row's most recent record with ``on`` <= trading date."""
    r = right.dropna(subset=[on]).sort_values(on)
    left = panel.reset_index().sort_values("Date")
    merged = pd.merge_asof(left, r, left_on="Date", right_on=on, direction="backward")
    return merged.set_index("Date")


def _build_panel(prices, rates, fin_wide, shares=None) -> pd.DataFrame:
    """Merge everything onto the stock's trading calendar.

    - interest rates: reindexed onto trading days and forward-filled (rates are
      step functions -- carry the last quote forward over non-quoted days).
    - financials & shares: an *as-of* merge keyed on ``filed`` (the date each
      report became public). This attaches the most recently *known* fundamentals
      to each trading day -> point-in-time, no look-ahead bias.
    """
    panel = prices.copy()

    if rates is not None and not rates.empty:
        aligned = rates.reindex(panel.index.union(rates.index)).sort_index().ffill()
        panel = panel.join(aligned.reindex(panel.index))

    if fin_wide is not None and not fin_wide.empty and fin_wide.get("filed") is not None \
            and fin_wide["filed"].notna().any():
        panel = _asof_join(panel, fin_wide.reset_index(), on="filed")

    if shares is not None and not shares.empty:
        # Shares carry their own 'filed'; rename so it doesn't clash with the
        # financials 'filed' already on the panel.
        sh = shares.rename(columns={"filed": "_shares_filed"})
        panel = _asof_join(panel, sh, on="_shares_filed").drop(columns=["_shares_filed"])

    return panel


def run_pipeline(
    query: str,
    start=None,
    end=None,
    out_dir: str = "output",
    fmt: str = "excel",
    export: bool = True,
    price_source: str | None = None,
    metrics: bool = True,
    rates=None,
) -> Result:
    """Download and align all data for ``query`` (a company name or ticker).

    Parameters
    ----------
    query : company name (e.g. "Apple") or ticker (e.g. "AAPL").
    start, end : optional date bounds (anything pandas can parse).
    out_dir : directory for output files.
    fmt : "excel" (single .xlsx workbook) or "csv" (a folder of CSVs).
    export : set False to get the data back without writing any files.
    price_source : force a price backend ("tiingo" or "yfinance"); default auto.
    metrics : also compute derived metrics (TTM, PE, PB, ROE, ...) on the panel.
    rates : a pre-fetched FRED DataFrame to reuse (batch runs pass this to avoid
        re-downloading the same rates per company); ``None`` fetches them here.
    """
    company = resolve(query)
    source = resolve_source(price_source)
    prices = get_prices(company.ticker, start, end, source=source)

    if rates is None:
        # Bound the macro data to the price history when explicit dates aren't given.
        try:
            rates = get_rates(start=start or prices.index.min(), end=end or prices.index.max())
        except Exception as exc:  # missing key / network -> continue without rates
            warnings.warn(f"[rates] skipped: {exc}")
            rates = pd.DataFrame()

    try:
        financials, financials_wide, shares = get_financials(company.cik)
    except Exception as exc:  # non-US filer / network -> continue without financials
        warnings.warn(f"[financials] skipped: {exc}")
        financials, financials_wide, shares = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    shares = split_adjust_shares(shares, company.ticker, source)
    panel = _build_panel(prices, rates, financials_wide, shares)
    if metrics and not financials.empty:
        panel = add_metrics(panel, financials)

    result = Result(company, prices, rates, financials, financials_wide, panel)
    if export:
        result.files = _export(result, out_dir, fmt)
    return result


def _export(result: Result, out_dir: str, fmt: str) -> list:
    """Write the result to an Excel workbook or a folder of CSVs."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = result.company.ticker
    about = pd.DataFrame([asdict(result.company)])
    sheets = {
        "prices": result.prices,
        "rates": result.rates,
        "financials": result.financials,
        "financials_wide": result.financials_wide,
        "panel": result.panel,
    }
    written: list = []

    if fmt == "excel":
        path = out / f"{stem}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as xl:
            about.to_excel(xl, sheet_name="about", index=False)
            for name, df in sheets.items():
                frame = df if not df.empty else pd.DataFrame({"note": ["no data"]})
                frame.to_excel(xl, sheet_name=name[:31])
        written.append(str(path))
    elif fmt == "csv":
        folder = out / stem
        folder.mkdir(exist_ok=True)
        about.to_csv(folder / "about.csv", index=False)
        for name, df in sheets.items():
            path = folder / f"{name}.csv"
            df.to_csv(path)
            written.append(str(path))
    else:
        raise ValueError(f"Unknown format {fmt!r}; use 'excel' or 'csv'.")

    return written
