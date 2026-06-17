"""
Download stock data with yfinance and save it as CSV files.

This project downloads three types of data for each ticker symbol:
1. Daily stock price history
2. Quarterly financial statements
3. Market capitalization

Example:
    python main.py AAPL MSFT TSLA
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf


# All CSV files will be saved inside this folder.
OUTPUT_DIR = Path("output")


def clean_ticker_symbol(ticker: str) -> str:
    """Return a ticker symbol in a consistent format."""
    return ticker.strip().upper()


def save_dataframe_to_csv(dataframe: pd.DataFrame, file_path: Path) -> None:
    """
    Save a pandas DataFrame to CSV.

    The output folder is created automatically if it does not already exist.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(file_path)


def download_price_history(ticker_symbol: str, period: str) -> pd.DataFrame:
    """Download historical daily stock prices for one ticker."""
    ticker = yf.Ticker(ticker_symbol)

    # auto_adjust=False keeps columns such as Open, High, Low, Close,
    # Adj Close, and Volume easy for beginners to recognize.
    history = ticker.history(period=period, auto_adjust=False)

    if history.empty:
        raise ValueError(f"No price history was returned for {ticker_symbol}.")

    return history


def download_quarterly_financial_statements(ticker_symbol: str) -> dict[str, pd.DataFrame]:
    """
    Download quarterly financial statement tables for one ticker.

    yfinance returns these tables with financial line items as rows and
    quarter dates as columns.
    """
    ticker = yf.Ticker(ticker_symbol)

    return {
        "quarterly_income_statement": ticker.quarterly_financials,
        "quarterly_balance_sheet": ticker.quarterly_balance_sheet,
        "quarterly_cash_flow": ticker.quarterly_cashflow,
    }


def download_market_cap(ticker_symbol: str) -> pd.DataFrame:
    """Download the latest available market capitalization for one ticker."""
    ticker = yf.Ticker(ticker_symbol)

    # fast_info is usually quicker than info because it requests less data.
    market_cap = ticker.fast_info.get("market_cap")

    # Some tickers may not have market_cap in fast_info, so try info as a backup.
    if market_cap is None:
        market_cap = ticker.info.get("marketCap")

    if market_cap is None:
        raise ValueError(f"No market capitalization was returned for {ticker_symbol}.")

    downloaded_at = datetime.now(timezone.utc).isoformat()

    return pd.DataFrame(
        [
            {
                "ticker": ticker_symbol,
                "market_cap": market_cap,
                "downloaded_at_utc": downloaded_at,
            }
        ]
    )


def download_ticker_data(ticker_symbol: str, period: str, output_dir: Path) -> None:
    """Download all requested data for one ticker and save it as CSV files."""
    print(f"Downloading data for {ticker_symbol}...")

    price_history = download_price_history(ticker_symbol, period)
    save_dataframe_to_csv(
        price_history,
        output_dir / f"{ticker_symbol}_price_history.csv",
    )

    financial_statements = download_quarterly_financial_statements(ticker_symbol)
    for statement_name, statement_data in financial_statements.items():
        if statement_data.empty:
            print(f"  Warning: {statement_name} was empty for {ticker_symbol}.")
            continue

        save_dataframe_to_csv(
            statement_data,
            output_dir / f"{ticker_symbol}_{statement_name}.csv",
        )

    market_cap = download_market_cap(ticker_symbol)
    save_dataframe_to_csv(
        market_cap,
        output_dir / f"{ticker_symbol}_market_cap.csv",
    )

    print(f"Finished {ticker_symbol}.")


def parse_arguments() -> argparse.Namespace:
    """Read ticker symbols and options from the command line."""
    parser = argparse.ArgumentParser(
        description="Download stock prices, quarterly financials, and market cap CSV files."
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        default=["AAPL", "MSFT"],
        help="Ticker symbols to download. Defaults to AAPL MSFT.",
    )
    parser.add_argument(
        "--period",
        default="5y",
        help="Price history period, such as 1y, 5y, 10y, or max. Defaults to 5y.",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR),
        help="Folder where CSV files will be saved. Defaults to output.",
    )

    return parser.parse_args()


def main() -> None:
    """Start the downloader."""
    args = parse_arguments()
    output_dir = Path(args.output)
    tickers = [clean_ticker_symbol(ticker) for ticker in args.tickers]

    for ticker_symbol in tickers:
        try:
            download_ticker_data(ticker_symbol, args.period, output_dir)
        except Exception as error:
            # Keep going if one ticker fails, so a problem with one symbol does
            # not stop the whole batch.
            print(f"Error downloading {ticker_symbol}: {error}")

    print(f"CSV files were saved in: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
