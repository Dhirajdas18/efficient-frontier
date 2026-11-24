import numpy as np
import pandas as pd
import pytest

from ef.assets import combine, drop_bad_prints


def test_bad_print_days_are_blanked_and_carried_forward():
    idx = pd.to_datetime(["2019-12-18", "2019-12-19", "2019-12-20", "2019-12-23"])
    px = pd.DataFrame({"gold": [33.5, 0.3, 0.3, 33.7]}, index=idx)
    out = drop_bad_prints(px, {"gold": [("2019-12-19", "2019-12-20")]})
    assert list(out["gold"]) == [33.5, 33.5, 33.5, 33.7]


def test_us_equity_is_converted_to_rupees():
    idx = pd.bdate_range("2024-01-01", periods=3)
    yahoo = pd.DataFrame({"NIFTY 50": [1.0, 1.0, 1.0], "gold": [1.0, 1.0, 1.0],
                          "S&P 500 (USD)": [100.0, 110.0, 110.0], "USDINR": [80.0, 80.0, 88.0]},
                         index=idx)
    lake = pd.DataFrame({"government bonds": [1.0, 1.0, 1.0], "cash": [1.0, 1.0, 1.0]}, index=idx)
    out = combine(yahoo, lake)
    assert out["US equity (INR)"].pct_change().iloc[1] == pytest.approx(0.10)
    assert out["US equity (INR)"].pct_change().iloc[2] == pytest.approx(0.10)  # rupee fell 10%
    assert np.isfinite(out.to_numpy()).all()


def test_missing_assets_names_absent_and_empty_columns():
    import numpy as np
    import pandas as pd

    from ef.assets import TICKERS, missing_assets

    names = list(TICKERS.values())
    full = pd.DataFrame(1.0, index=range(3), columns=names)
    assert missing_assets(full) == []
    gap = full.drop(columns=names[0]).assign(**{names[1]: np.nan})
    assert missing_assets(gap) == [names[0], names[1]]


def test_fetch_yahoo_retries_until_complete(monkeypatch):
    import pandas as pd

    import ef.assets as a

    names = list(a.TICKERS.values())
    calls = []

    def fake(start):
        calls.append(start)
        cols = names if len(calls) > 1 else names[1:]  # first try drops a ticker
        return pd.DataFrame(1.0, index=pd.DatetimeIndex(["2024-01-01"]), columns=cols)

    monkeypatch.setattr(a, "_download_yahoo", fake)
    monkeypatch.setattr(a.time, "sleep", lambda s: None)
    assert list(a.fetch_yahoo().columns) == names and len(calls) == 2
