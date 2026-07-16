"""Command-line entry point.

    python -m pfpa AAPL                     # one company
    python -m pfpa AAPL MSFT NVDA           # several -> also writes portfolio.*
    python -m pfpa --file tickers.txt       # read companies from a file
"""
from __future__ import annotations

import argparse

from .batch import run_batch
from .pipeline import run_pipeline


def _load_queries(args) -> list:
    queries = list(args.query)
    if args.file:
        with open(args.file) as fh:
            queries += [
                line.strip()
                for line in fh
                if line.strip() and not line.lstrip().startswith("#")
            ]
    return queries


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="pfpa",
        description="Download & align stock prices, financials and interest rates for any company.",
    )
    parser.add_argument("query", nargs="*", help="Company name(s) or ticker(s), e.g. AAPL MSFT")
    parser.add_argument("--file", help="Text file with one company per line (# comments ok)")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--out", default="output", help="Output directory (default: ./output)")
    parser.add_argument(
        "--format", choices=["excel", "csv"], default="excel", dest="fmt",
        help="Output format (default: excel)",
    )
    parser.add_argument(
        "--source", choices=["tiingo", "yfinance"], default=None,
        help="Price backend (default: tiingo if TIINGO_API_KEY set, else yfinance)",
    )
    parser.add_argument("--no-metrics", action="store_true", help="Skip derived metrics")
    args = parser.parse_args(argv)

    queries = _load_queries(args)
    if not queries:
        parser.error("provide at least one company (positional args or --file)")

    common = dict(
        start=args.start, end=args.end, out_dir=args.out, fmt=args.fmt,
        price_source=args.source, metrics=not args.no_metrics,
    )

    if len(queries) == 1:
        _report_one(run_pipeline(queries[0], **common))
    else:
        results = run_batch(queries, **common)
        _report_batch(results, args.out)


def _report_one(result) -> None:
    c = result.company
    n_concepts = 0 if result.financials.empty else result.financials["concept"].nunique()
    print(f"Resolved:   {c.name} ({c.ticker}, CIK {c.cik})")
    print(f"Prices:     {len(result.prices):>6} trading days")
    print(f"Rates:      {result.rates.shape[1]:>6} series")
    print(f"Financials: {n_concepts:>6} concepts")
    print(f"Panel:      {result.panel.shape[0]:>6} rows x {result.panel.shape[1]} cols")
    for path in result.files:
        print(f"  wrote {path}")


def _report_batch(results: dict, out_dir: str) -> None:
    print(f"Processed {len(results)} companies: {', '.join(results)}")
    for ticker, res in results.items():
        print(f"  {ticker:6} {res.panel.shape[0]:>5} rows  ({res.company.name})")
    if results:
        print(f"Combined portfolio written under {out_dir}/portfolio.*")


if __name__ == "__main__":
    main()
