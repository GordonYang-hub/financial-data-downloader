"""Central configuration: environment-driven settings, HTTP headers, defaults.

Everything the pipeline needs to be configured lives here so the rest of the
code stays free of magic constants. Values come from environment variables
(optionally loaded from a local ``.env`` file), so nothing secret is hardcoded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load a local .env if python-dotenv is installed (optional convenience).
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv not installed -> rely on real environment variables
    pass


# Default interest-rate / macro series pulled from FRED.
# Mapping: FRED series id -> friendly column name used in the output.
# All of these are *daily* business-day series so they line up with trading days.
DEFAULT_FRED_SERIES = {
    "DGS3MO": "UST_3M",        # 3-Month Treasury constant maturity
    "DGS2": "UST_2Y",          # 2-Year Treasury
    "DGS10": "UST_10Y",        # 10-Year Treasury
    "DFF": "FedFunds",         # Effective Federal Funds Rate (daily)
    "T10Y2Y": "Spread_10Y_2Y",  # 10Y-2Y term spread
}


@dataclass
class Settings:
    """Runtime settings, populated from the environment with sensible defaults."""

    # Free FRED key: https://fredaccount.stlouisfed.org/apikeys
    fred_api_key: str = field(default_factory=lambda: os.getenv("FRED_API_KEY", ""))

    # Free Tiingo key: https://www.tiingo.com  (optional). When set, prices come
    # from Tiingo's official API; otherwise the pipeline falls back to yfinance.
    tiingo_api_key: str = field(default_factory=lambda: os.getenv("TIINGO_API_KEY", ""))

    # SEC's fair-access policy requires a descriptive User-Agent with a contact
    # email. Override via SEC_USER_AGENT. See https://www.sec.gov/os/webmaster-faq#code-support
    sec_user_agent: str = field(
        default_factory=lambda: os.getenv("SEC_USER_AGENT", "PFPA research syu224@ucsc.edu")
    )

    fred_series: dict = field(default_factory=lambda: dict(DEFAULT_FRED_SERIES))
    cache_dir: Path = field(
        default_factory=lambda: Path(os.getenv("PFPA_CACHE", Path.home() / ".pfpa_cache"))
    )
    request_timeout: int = 30

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)


# A single shared instance the rest of the package imports.
settings = Settings()
