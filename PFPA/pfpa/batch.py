"""Run the pipeline over many companies at once.

Rates are the same for every company, so they're downloaded once and reused.
Each company is still written individually; in addition a combined ``portfolio``
output is produced: a cross-sectional ``summary`` (latest metrics per company)
and a stacked ``panel_all`` (every daily panel with a ``Symbol`` column) -- both
handy for cross-company research.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from .pipeline import Result, run_pipeline
from .rates import get_rates

_SUMMARY_COLS = [
    "Close", "MarketCap", "PE", "PS", "PB", "ROE", "ROA", "NetMargin",
    "Revenue_TTM", "NetIncome_TTM",
]


def run_batch(
    queries,
    start=None,
    end=None,
    out_dir: str = "output",
    fmt: str = "excel",
    price_source: str | None = None,
    metrics: bool = True,
    combine: bool = True,
) -> dict:
    """Process each of ``queries`` and return ``{ticker: Result}``.

    A company that fails to resolve or download is skipped with a warning, so
    one bad name never aborts the whole batch.
    """
    try:
        rates = get_rates(start=start, end=end)  # once, shared across companies
    except Exception as exc:
        warnings.warn(f"[rates] skipped: {exc}")
        rates = pd.DataFrame()

    results: dict = {}
    for query in queries:
        try:
            res = run_pipeline(
                query, start=start, end=end, out_dir=out_dir, fmt=fmt, export=True,
                price_source=price_source, metrics=metrics, rates=rates,
            )
            results[res.company.ticker] = res
        except Exception as exc:
            warnings.warn(f"[{query}] skipped: {exc}")

    if combine and results:
        _export_combined(results, out_dir, fmt)
    return results


def _summary(results: dict) -> pd.DataFrame:
    rows = []
    for ticker, res in results.items():
        panel = res.panel
        row = {"Symbol": ticker, "Name": res.company.name, "Date": None}
        if len(panel):
            last = panel.iloc[-1]
            row["Date"] = panel.index[-1]
            for col in _SUMMARY_COLS:
                row[col] = last[col] if col in panel.columns else None
        rows.append(row)
    return pd.DataFrame(rows).set_index("Symbol")


def _panel_all(results: dict) -> pd.DataFrame:
    frames = []
    for ticker, res in results.items():
        panel = res.panel.copy()
        panel.insert(0, "Symbol", ticker)
        frames.append(panel)
    return pd.concat(frames).reset_index()


def _export_combined(results: dict, out_dir: str, fmt: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary, panel_all = _summary(results), _panel_all(results)

    if fmt == "excel":
        path = out / "portfolio.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as xl:
            summary.to_excel(xl, sheet_name="summary")
            panel_all.to_excel(xl, sheet_name="panel_all", index=False)
    else:
        folder = out / "portfolio"
        folder.mkdir(exist_ok=True)
        summary.to_csv(folder / "summary.csv")
        panel_all.to_csv(folder / "panel_all.csv", index=False)
