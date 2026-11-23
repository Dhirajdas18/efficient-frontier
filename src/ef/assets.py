"""Asset classes for an Indian investor, in rupees.

- NIFTY 50: NIFTYBEES ETF (dividends included), Yahoo.
- gold: GOLDBEES ETF, Yahoo.
- US equity (INR): S&P 500 total-return index × USD/INR, Yahoo.
- government bonds: NSE's Nifty Composite G-sec Index (total return), from the local lake.
- cash: NSE's Nifty 1D Rate Index (overnight money market), from the local lake.

Yahoo printed NIFTYBEES and GOLDBEES at a tenth and a hundredth of their price on 19-20 Dec 2019
(the price is back the next trading day); those days are blanked and carried forward.
"""

import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASSETS_PATH = ROOT / "data" / "assets.parquet"
TICKERS = {"NIFTYBEES.NS": "NIFTY 50", "GOLDBEES.NS": "gold", "^SP500TR": "S&P 500 (USD)",
           "USDINR=X": "USDINR"}
BAD_PRINTS = {"NIFTY 50": [("2019-12-19", "2019-12-20")], "gold": [("2019-12-19", "2019-12-20")]}
LAKE_INDICES = {"Nifty Composite G-sec Index": "government bonds", "Nifty 1D Rate Index": "cash"}
CLASSES = ["NIFTY 50", "gold", "government bonds", "US equity (INR)"]


def fetch_yahoo(start: str = "2015-01-01") -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(list(TICKERS), start=start, auto_adjust=False, progress=False,
                      threads=False)["Adj Close"].rename(columns=TICKERS)
    raw.index = pd.DatetimeIndex(raw.index.tz_localize(None), name="date")
    return raw


def drop_bad_prints(px: pd.DataFrame, bad: dict = BAD_PRINTS) -> pd.DataFrame:
    px = px.copy()
    for col, spans in bad.items():
        if col in px:
            for a, b in spans:
                px.loc[a:b, col] = float("nan")
    return px.ffill()


def load_lake_indices(lake_dir: str | Path | None = None) -> pd.DataFrame:
    lake_dir = Path(lake_dir or os.environ.get("EF_LAKE_DIR", ""))
    frames = [pd.read_parquet(f, columns=["date", "index", "close"])
              for f in sorted((lake_dir / "index").glob("*.parquet"))]
    x = pd.concat(frames)
    x = x[x["index"].isin(LAKE_INDICES)]
    out = x.pivot_table(index="date", columns="index", values="close").rename(
        columns=LAKE_INDICES)
    out.index = pd.to_datetime(out.index)
    return out


def combine(yahoo: pd.DataFrame, lake: pd.DataFrame) -> pd.DataFrame:
    """One daily price table in rupees: weekdays where every series has started, gaps (holidays
    in one market) carried forward."""
    px = pd.concat([drop_bad_prints(yahoo), lake], axis=1).sort_index().ffill()
    px["US equity (INR)"] = px["S&P 500 (USD)"] * px["USDINR"]
    px = px[px.index.day_of_week < 5]
    return px.dropna()
