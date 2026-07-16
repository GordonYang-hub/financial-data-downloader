"""Resolve a company *name or ticker* to ``{ticker, cik, name}``.

Uses SEC's official ticker->CIK mapping (``company_tickers.json``), which is the
authoritative source for US-listed filers and doubles as a name search index.
The file is small and changes rarely, so it is cached on disk.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher

import requests

from .config import settings

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


@dataclass
class Company:
    """A resolved company identity."""

    ticker: str  # upper-case, e.g. "AAPL"
    cik: str     # 10-digit zero-padded CIK, e.g. "0000320193"
    name: str    # official company title, e.g. "Apple Inc."


def _load_map() -> list[dict]:
    """Return SEC's ticker/CIK/name records, cached on disk."""
    cache = settings.cache_dir / "company_tickers.json"
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        resp = requests.get(
            _TICKERS_URL,
            headers={"User-Agent": settings.sec_user_agent},
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        cache.write_text(json.dumps(data))
    return list(data.values())


def _to_company(row: dict) -> Company:
    return Company(
        ticker=row["ticker"].upper(),
        cik=str(row["cik_str"]).zfill(10),
        name=row["title"],
    )


def resolve(query: str) -> Company:
    """Resolve ``query`` (a ticker or a company name) to a :class:`Company`.

    Matching order:
      1. exact ticker match (case-insensitive)
      2. best fuzzy match against company names (substring or difflib ratio)

    Raises ``ValueError`` if nothing plausible is found.
    """
    q = query.strip()
    rows = _load_map()

    # 1) exact ticker match
    for row in rows:
        if row["ticker"].upper() == q.upper():
            return _to_company(row)

    # 2) fuzzy name match
    ql = q.lower()
    best, score = None, 0.0
    for row in rows:
        title = row["title"].lower()
        s = 1.0 if ql in title else SequenceMatcher(None, ql, title).ratio()
        if s > score:
            best, score = row, s

    if best is None or score < 0.4:
        raise ValueError(f"Could not resolve a company for query: {query!r}")
    return _to_company(best)
