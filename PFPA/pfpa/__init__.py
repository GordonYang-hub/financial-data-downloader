"""PFPA -- a small, provider-abstracted financial-data pipeline.

Enter a company name or ticker; the pipeline downloads stock prices (Stooq),
fundamentals (SEC EDGAR) and interest rates (FRED), aligns them on the stock's
trading calendar, and returns / exports the result.

Quick start
-----------
    from pfpa import run_pipeline
    result = run_pipeline("AAPL", start="2015-01-01", fmt="csv")
    result.panel.head()      # daily price + rates + point-in-time fundamentals

Each data source lives in its own module (``prices``, ``financials``,
``rates``) behind a plain function, so swapping in another provider is a
one-file change.
"""
from .batch import run_batch
from .metrics import add_metrics
from .pipeline import Result, run_pipeline
from .resolve import Company, resolve

__all__ = ["run_pipeline", "run_batch", "add_metrics", "Result", "resolve", "Company"]
__version__ = "0.2.0"
