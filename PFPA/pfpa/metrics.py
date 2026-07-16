"""Derived metrics: trailing-twelve-month (TTM) fundamentals and the common
valuation / profitability ratios, all computed point-in-time on the daily panel.

Flow items (revenue, net income, ...) are reported per quarter, so a meaningful
PE/PS/margin needs a TTM figure. SEC does not report a standalone Q4 (the 10-K
carries the full year), so Q4 is reconstructed as ``FY - (Q1 + Q2 + Q3)`` and
TTM is a rolling 4-quarter sum. Each TTM value is dated by when its newest
quarter was *filed*, so the as-of merge onto trading days stays look-ahead free.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Flow concepts we build a TTM series for (must exist in financials.CONCEPTS).
TTM_CONCEPTS = ["Revenue", "NetIncome"]


def _quarterly(long_df: pd.DataFrame, concept: str) -> pd.DataFrame:
    """Chronological single-quarter series for a flow ``concept`` with Q4 rebuilt.

    Returns columns ``end``, ``filed``, ``value`` sorted by period end.

    Facts are deduped by *period end* keeping the earliest filing (as first
    reported). We must NOT key on ``fy``/``fp``: those describe the filing's
    fiscal context, so a quarter reappearing as a prior-year comparative in a
    later filing carries a different fy/fp and would otherwise slip through as a
    duplicate. Q4 is backed out by matching quarters to the annual period's date
    window, again independent of the fy/fp labels.
    """
    df = long_df[
        (long_df["concept"] == concept)
        & long_df["form"].str.startswith(("10-K", "10-Q"), na=False)
    ]
    if df.empty:
        return pd.DataFrame(columns=["end", "filed", "value"])

    cols = ["start", "end", "filed", "value"]
    # Per period end pick the preferred tag (rank), then the earliest filing.
    order = ["end", "rank", "filed"]
    # Single quarter (~3 months): one row per period end, as first reported.
    q = (
        df[df["months"].between(2, 4)]
        .sort_values(order).drop_duplicates("end", keep="first")[cols]
    )
    # Full year (~12 months) from the 10-K: one row per period end.
    a = (
        df[df["months"].between(11, 13)]
        .sort_values(order).drop_duplicates("end", keep="first")[cols]
    )

    rows = q[["end", "filed", "value"]].to_dict("records")
    for _, ann in a.iterrows():
        within = q[(q["end"] > ann["start"]) & (q["end"] <= ann["end"])]
        if len(within) == 3:  # Q4 = full year minus the three interim quarters
            rows.append(
                {"end": ann["end"], "filed": ann["filed"], "value": ann["value"] - within["value"].sum()}
            )

    out = pd.DataFrame(rows).dropna(subset=["end", "filed"])
    out = out.sort_values(["end", "filed"]).drop_duplicates("end", keep="first")
    return out.sort_values("end").reset_index(drop=True)


def ttm(long_df: pd.DataFrame, concept: str) -> pd.Series:
    """TTM series for a flow ``concept``, indexed by availability (filed) date."""
    q = _quarterly(long_df, concept)
    if len(q) < 4:
        return pd.Series(dtype="float64")
    q["ttm"] = q["value"].rolling(4).sum()
    s = q.dropna(subset=["ttm"]).set_index("filed")["ttm"]
    return s[~s.index.duplicated(keep="last")].sort_index()


def _safe_div(a, b):
    if a is None or b is None:
        return np.nan
    return (a / b).replace([np.inf, -np.inf], np.nan)


def add_metrics(panel: pd.DataFrame, long_df: pd.DataFrame) -> pd.DataFrame:
    """Append TTM fundamentals and ratio columns to a daily ``panel``.

    Adds: Revenue_TTM, NetIncome_TTM, MarketCap, PE, PS, PB, ROE, ROA,
    NetMargin, CurrentRatio. Ratios reuse the panel's point-in-time balance-sheet
    columns, so everything stays consistent as of each trading day.
    """
    panel = panel.copy()

    # TTM flows, as-of merged onto trading days by filed date.
    for concept in TTM_CONCEPTS:
        col = f"{concept}_TTM"
        series = ttm(long_df, concept)
        if series.empty:
            panel[col] = np.nan
            continue
        right = series.rename(col).reset_index().rename(columns={"filed": "_f"}).sort_values("_f")
        left = panel.reset_index().sort_values("Date")
        merged = pd.merge_asof(left, right, left_on="Date", right_on="_f", direction="backward")
        panel[col] = merged.set_index("Date")[col]

    close = panel.get("Close")
    shares = panel.get("SharesOutstanding")
    if close is not None and shares is not None:
        panel["MarketCap"] = close * shares

    mc = panel.get("MarketCap")
    ni = panel.get("NetIncome_TTM")
    rev = panel.get("Revenue_TTM")
    panel["PE"] = _safe_div(mc, ni)
    panel["PS"] = _safe_div(mc, rev)
    panel["PB"] = _safe_div(mc, panel.get("Equity"))
    panel["ROE"] = _safe_div(ni, panel.get("Equity"))
    panel["ROA"] = _safe_div(ni, panel.get("Assets"))
    panel["NetMargin"] = _safe_div(ni, rev)
    panel["CurrentRatio"] = _safe_div(panel.get("CurrentAssets"), panel.get("CurrentLiabilities"))
    return panel
