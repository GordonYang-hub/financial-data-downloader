"""Company fundamentals from SEC EDGAR's XBRL "company facts" API.

Endpoint: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
Official, free, no API key -- only a descriptive User-Agent is required.

We pull a curated set of common income-statement / balance-sheet / cash-flow
line items. Two realities make this fiddly, and are handled here:

* Companies tag the same economic concept with different (or changing) US-GAAP
  names over time, so each concept maps to a list of candidate tags and we MERGE
  all of them (preferring the first that has a value for a given period).
* Shares outstanding is reported on every filing's cover page (dei tag) but as an
  instant dated near the *filing* date, not the period end -- so it is extracted
  separately and joined point-in-time on its own, rather than mixed into the
  period-end statement table.
"""
from __future__ import annotations

import pandas as pd
import requests

from .config import settings

_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_TAXONOMIES = ("us-gaap", "ifrs-full", "dei")

# Friendly name -> candidate XBRL tags, highest precedence first. All candidates
# are merged; for any given period the first tag that reports a value wins.
CONCEPTS: dict = {
    "Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "CostOfRevenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "GrossProfit": ["GrossProfit"],
    "OperatingIncome": ["OperatingIncomeLoss"],
    "NetIncome": ["NetIncomeLoss"],
    "EPSDiluted": ["EarningsPerShareDiluted"],
    "Assets": ["Assets"],
    "CurrentAssets": ["AssetsCurrent"],
    "Liabilities": ["Liabilities"],
    "CurrentLiabilities": ["LiabilitiesCurrent"],
    "Equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "Cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "OperatingCashFlow": ["NetCashProvidedByUsedInOperatingActivities"],
}

# Shares outstanding: cover-page dei tag first (reported every filing), then the
# balance-sheet tags as a fallback.
_SHARES_TAGS = [
    "EntityCommonStockSharesOutstanding",
    "CommonStockSharesOutstanding",
    "CommonStockSharesIssued",
]


def _facts(cik: str) -> dict:
    resp = requests.get(
        _FACTS_URL.format(cik=cik),
        headers={"User-Agent": settings.sec_user_agent},
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    return resp.json().get("facts", {})


def _pick_unit(units: dict) -> str:
    return next((u for u in ("USD", "USD/shares", "shares") if u in units), next(iter(units)))


def _records(facts: dict, tags: list, name: str) -> list:
    """Collect observations for every candidate tag (each from the first taxonomy
    that carries it), tagging each with its precedence ``rank`` (0 = preferred)."""
    blocks = [facts.get(t, {}) for t in _TAXONOMIES]
    out = []
    for rank, tag in enumerate(tags):
        for block in blocks:
            if tag not in block:
                continue
            units = block[tag]["units"]
            unit = _pick_unit(units)
            for e in units[unit]:
                out.append(
                    {
                        "concept": name,
                        "value": e.get("val"),
                        "start": e.get("start"),
                        "end": e.get("end"),
                        "fy": e.get("fy"),
                        "fp": e.get("fp"),
                        "form": e.get("form"),
                        "filed": e.get("filed"),
                        "unit": unit,
                        "rank": rank,
                    }
                )
            break  # take this tag from the first taxonomy that has it
    return out


def _shares_frame(facts: dict) -> pd.DataFrame:
    """Point-in-time shares outstanding: one value per filing, keyed by filed."""
    recs = _records(facts, _SHARES_TAGS, "Shares")
    cols = ["filed", "SharesOutstanding"]
    if not recs:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(recs)
    df["end"] = pd.to_datetime(df["end"], errors="coerce")
    df["filed"] = pd.to_datetime(df["filed"], errors="coerce")
    df = df.dropna(subset=["filed", "value"])
    # One value per filing: prefer the primary tag, then the most recent as-of date.
    df = df.sort_values(["filed", "rank", "end"]).drop_duplicates("filed", keep="last")
    return (
        df.rename(columns={"value": "SharesOutstanding"})[cols]
        .sort_values("filed")
        .reset_index(drop=True)
    )


def get_financials(cik: str):
    """Return ``(long_df, wide_df, shares_df)`` for a CIK.

    ``long_df`` -- tidy: one row per (concept, period, tag). All filings kept.
    ``wide_df`` -- one row per reporting ``PeriodEnd``, one column per concept,
        plus ``filed`` / ``form`` / ``fp``.
    ``shares_df`` -- point-in-time shares outstanding (``filed`` -> value).
    """
    facts = _facts(cik)
    shares = _shares_frame(facts)

    rows = []
    for name, tags in CONCEPTS.items():
        rows.extend(_records(facts, tags, name))
    if not rows:
        return pd.DataFrame(), pd.DataFrame(), shares

    long_df = pd.DataFrame(rows)
    for col in ("start", "end", "filed"):
        long_df[col] = pd.to_datetime(long_df[col], errors="coerce")
    # Reporting-period length in months; instant/balance-sheet facts -> 0.
    long_df["months"] = ((long_df["end"] - long_df["start"]).dt.days / 30).round()
    long_df["months"] = long_df["months"].fillna(0)
    long_df = long_df.sort_values(["concept", "end", "filed"]).reset_index(drop=True)

    # Reduce to one value per concept+period-end with deterministic rules:
    #   1) Duration: flow items report both a 3-month and a year-to-date figure
    #      for the same end. Take the single quarter for Q1-Q3 and the full year
    #      for FY, so each row is a clean, comparable period.
    #   2) Tag precedence: prefer the primary candidate tag (rank 0).
    #   3) Filing: keep the value as *first* reported (earliest filed) -- the
    #      point-in-time convention. This ignores later restatements and the trap
    #      where a period reappears as a comparative in a much later filing.
    stmt = long_df[long_df["form"].str.startswith(("10-K", "10-Q"), na=False)].copy()
    is_fy = stmt["fp"].eq("FY")
    stmt["_dur"] = stmt["months"].where(~is_fy, -stmt["months"])  # short qtr / long year
    stmt = stmt.sort_values(["concept", "end", "_dur", "rank", "filed"])
    stmt = stmt.drop_duplicates(subset=["concept", "end"], keep="first")

    wide = stmt.pivot_table(index="end", columns="concept", values="value", aggfunc="last")
    # When each period-end first became publicly known.
    meta = stmt.groupby("end").agg(
        filed=("filed", "max"), fp=("fp", "last"), form=("form", "last")
    )
    wide = wide.join(meta).sort_index()
    wide.index.name = "PeriodEnd"
    return long_df, wide, shares
