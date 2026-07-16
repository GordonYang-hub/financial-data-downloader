"""Daily OHLCV stock prices, with two interchangeable backends.

* ``tiingo``   -- Tiingo's official REST API. Reliable, clean, free API key
                  (https://www.tiingo.com). Used by default when TIINGO_API_KEY
                  is set. This is the "official terminal" path.
* ``yfinance`` -- Yahoo Finance via the community ``yfinance`` library. No key,
                  works out of the box; used as the default fallback.

Both return the same schema so the rest of the pipeline never cares which one
ran. Swapping in yet another provider (Alpha Vantage, a paid terminal, ...) is
just another ``_from_*`` function.

Note: Stooq was the original plan but now serves a JavaScript proof-of-work
bot-wall to non-browser clients, so it can't be used programmatically.
"""
from __future__ import annotations

import pandas as pd
import requests

from .config import settings

# Canonical output columns, in order.
_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def resolve_source(source: str | None = None) -> str:
    """Which price backend to use: explicit ``source`` else Tiingo-if-keyed else yfinance."""
    return source or ("tiingo" if settings.tiingo_api_key else "yfinance")


def get_prices(ticker: str, start=None, end=None, source: str | None = None) -> pd.DataFrame:
    """Return daily prices indexed by trading ``Date`` (Open/High/Low/Close/Adj Close/Volume).

    ``source`` forces a backend ("tiingo" or "yfinance"); by default Tiingo is
    used when an API key is configured, otherwise yfinance.
    """
    source = resolve_source(source)
    if source == "tiingo":
        df = _from_tiingo(ticker, start, end)
    elif source == "yfinance":
        df = _from_yfinance(ticker, start, end)
    else:
        raise ValueError(f"Unknown price source {source!r}; use 'tiingo' or 'yfinance'.")

    df = df.reindex(columns=[c for c in _COLUMNS if c in df.columns])
    df.index.name = "Date"
    return df.sort_index()


def _from_tiingo(ticker: str, start, end) -> pd.DataFrame:
    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
    params = {"token": settings.tiingo_api_key, "format": "json", "resampleFreq": "daily"}
    if start is not None:
        params["startDate"] = pd.Timestamp(start).strftime("%Y-%m-%d")
    if end is not None:
        params["endDate"] = pd.Timestamp(end).strftime("%Y-%m-%d")

    resp = requests.get(url, params=params, timeout=settings.request_timeout)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise ValueError(f"Tiingo returned no price data for {ticker!r}")

    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
    return pd.DataFrame(
        {
            "Open": df["open"],
            "High": df["high"],
            "Low": df["low"],
            "Close": df["close"],
            "Adj Close": df["adjClose"],
            "Volume": df["volume"],
        }
    )


def _from_yfinance(ticker: str, start, end) -> pd.DataFrame:
    import yfinance as yf  # lazy import: only needed for this backend

    df = yf.download(
        ticker,
        start=_date(start),
        end=_date(end),
        progress=False,
        auto_adjust=False,
    )
    if df is None or df.empty:
        raise ValueError(f"yfinance returned no price data for {ticker!r}")
    # Single-ticker downloads come back with a (field, ticker) column MultiIndex.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _date(x):
    return None if x is None else pd.Timestamp(x).strftime("%Y-%m-%d")


def get_splits(ticker: str) -> pd.Series:
    """Stock-split events as ``{date: ratio}`` (e.g. a 10-for-1 split -> 10.0).

    Splits are corporate-action facts; we read them from yfinance regardless of
    the price backend. Returns an empty Series if the ticker never split.
    """
    import yfinance as yf

    s = yf.Ticker(ticker).splits
    if s is None or len(s) == 0:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime([str(d)[:10] for d in s.index])  # drop tz, keep the date
    return pd.Series(list(s.values), index=idx).sort_index()


def split_adjust_shares(shares: pd.DataFrame, ticker: str, source: str | None = None):
    """Put as-reported share counts on the same split-adjusted basis as the
    backend's Close, so ``price * shares`` is a correct market cap.

    yfinance's Close is split-adjusted, so a historical share count must be
    scaled by the splits that happened *after* it was filed. Tiingo's Close is
    raw, so its shares are already consistent and are left untouched.
    """
    if shares is None or shares.empty or resolve_source(source) != "yfinance":
        return shares
    try:
        splits = get_splits(ticker)
    except Exception:
        return shares
    if splits.empty:
        return shares
    factor = [float(splits[splits.index > d].prod()) or 1.0 for d in shares["filed"]]
    out = shares.copy()
    out["SharesOutstanding"] = out["SharesOutstanding"].to_numpy() * factor
    return out
