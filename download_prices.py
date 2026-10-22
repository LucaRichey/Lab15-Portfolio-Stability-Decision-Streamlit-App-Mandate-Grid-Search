"""
download_prices.py — Fetch 5 Years of Monthly Adjusted Close Prices
for Meridian / Project 2 Fund Universe (BIL, IEF, LQD, VT)

Standard format: Date first, oldest month first, one column per ticker.
"""

import os
import sys
import pandas as pd
import yfinance as yf

TICKERS = ["BIL", "IEF", "LQD", "VT"]
PERIOD = "5y"
INTERVAL = "1mo"
OUTPUT_PATH = "prices.csv"

def fetch_monthly_prices():
    print(f"Downloading 5-year monthly data for tickers: {TICKERS}...")
    df = yf.download(TICKERS, period=PERIOD, interval=INTERVAL, auto_adjust=False)
    
    # Extract 'Adj Close'
    if "Adj Close" in df:
        adj_close = df["Adj Close"].copy()
    else:
        print("Adj Close not found, using Close column.")
        adj_close = df["Close"].copy()

    # Reorder columns to match TICKERS
    adj_close = adj_close[TICKERS]
    
    # Drop rows with all NaNs (e.g. current incomplete month if any)
    adj_close = adj_close.dropna(how="all")
    
    # Format date as YYYY-MM-DD
    adj_close.index = adj_close.index.strftime("%Y-%m-%d")
    adj_close.index.name = "Date"
    
    # Sort oldest month first
    adj_close = adj_close.sort_index(ascending=True)
    
    # Save to CSV
    adj_close.to_csv(OUTPUT_PATH, float_format="%.2f")
    print(f"Saved {len(adj_close)} monthly observations to {OUTPUT_PATH}.")
    print("\nFirst 5 rows:")
    print(adj_close.head())
    print("\nLast 5 rows:")
    print(adj_close.tail())

if __name__ == "__main__":
    try:
        fetch_monthly_prices()
    except Exception as e:
        print(f"Error fetching prices via yfinance: {e}", file=sys.stderr)
        sys.exit(1)

