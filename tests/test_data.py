import pandas as pd

from ef.data import SECTORS, SYMBOLS, daily_returns


def test_constituent_snapshot_has_fifty_stocks_with_sectors():
    assert len(SYMBOLS) == 50 and len(set(SYMBOLS)) == 50
    assert set(SECTORS) == set(SYMBOLS)


def test_listed_yahoo_errors_are_neutralised():
    idx = pd.to_datetime(["2025-10-13", "2025-10-14", "2025-10-15"])
    px = pd.DataFrame({"TMPV": [660.8, 395.5, 390.9], "INFY": [100.0, 101.0, 102.0]}, index=idx)
    r = daily_returns(px)
    assert r.loc["2025-10-14", "TMPV"] == 0.0  # demerger day, listed in yahoo_fixes.csv
    assert r.loc["2025-10-15", "TMPV"] < 0 and r.loc["2025-10-14", "INFY"] > 0
