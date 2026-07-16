"""Interest-rate & macro series from FRED (Federal Reserve Bank of St. Louis).

FRED is the official, authoritative source for US interest rates. A free API
key is required: https://fredaccount.stlouisfed.org/apikeys
"""
from __future__ import annotations

import pandas as pd
import requests

from .config import settings

_BASE = "https://api.stlouisfed.org/fred/series/observations"


def get_series(series_id: str, start=None, end=None) -> pd.Series:
    """Fetch a single FRED series as a date-indexed float Series."""
    if not settings.fred_api_key:
        raise RuntimeError(
            "FRED_API_KEY is not set. Get a free key at "
            "https://fredaccount.stlouisfed.org/apikeys and put it in your "
            "environment or a .env file."
        )

    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
    }
    if start is not None:
        params["observation_start"] = pd.Timestamp(start).strftime("%Y-%m-%d")
    if end is not None:
        params["observation_end"] = pd.Timestamp(end).strftime("%Y-%m-%d")

    resp = requests.get(_BASE, params=params, timeout=settings.request_timeout)
    resp.raise_for_status()
    obs = resp.json().get("observations", [])

    idx = pd.to_datetime([o["date"] for o in obs])
    # FRED encodes missing values as ".", which coerces cleanly to NaN.
    vals = pd.to_numeric([o["value"] for o in obs], errors="coerce")
    return pd.Series(vals, index=idx, name=series_id)


def get_rates(series: dict | None = None, start=None, end=None) -> pd.DataFrame:
    """Fetch several FRED series into one date-indexed DataFrame.

    ``series`` maps FRED id -> friendly column name; defaults to
    :data:`pfpa.config.DEFAULT_FRED_SERIES`.
    """
    series = series or settings.fred_series
    cols = {name: get_series(sid, start, end) for sid, name in series.items()}
    df = pd.concat(cols, axis=1).sort_index()
    df.index.name = "Date"
    return df
