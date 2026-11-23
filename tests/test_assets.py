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
