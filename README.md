# Financial Data Downloader

This Python project downloads stock data with `yfinance` and saves the results as CSV files.

It downloads:

- Stock price history
- Quarterly income statements
- Quarterly balance sheets
- Quarterly cash flow statements
- Latest available market capitalization

The project supports ticker symbols such as `AAPL`, `MSFT`, and `TSLA`.

## Files

- `main.py` - The Python script that downloads the data.
- `requirements.txt` - The Python packages needed to run the project.
- `output/` - The folder where CSV files are saved after the script runs.

## Setup On Windows

Open PowerShell in this project folder:

```powershell
cd D:\Desktopfinancial-data-downloader
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required packages:

```powershell
pip install -r requirements.txt
```

## Run The Project

Run the default test tickers, `AAPL` and `MSFT`:

```powershell
python main.py
```

Run specific tickers:

```powershell
python main.py AAPL MSFT TSLA
```

Change the stock price history period:

```powershell
python main.py AAPL MSFT --period 10y
```

Choose a different output folder:

```powershell
python main.py AAPL MSFT --output my_csv_files
```

## Output Files

For each ticker, the script creates CSV files like these:

- `AAPL_price_history.csv`
- `AAPL_quarterly_income_statement.csv`
- `AAPL_quarterly_balance_sheet.csv`
- `AAPL_quarterly_cash_flow.csv`
- `AAPL_market_cap.csv`

The default output folder is `output`.

## Notes For Beginners

- A ticker symbol is the short code for a stock. For example, Apple is `AAPL`.
- CSV files can be opened in Excel, Google Sheets, or other spreadsheet tools.
- If one ticker fails, the script prints an error and continues with the next ticker.
- The data comes from Yahoo Finance through the `yfinance` package.
