import numpy as np
import pandas as pd
import pytest

from ef.walkforward import hold_returns, walk_forward


def _prices(n_days=400, n=6, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    r = rng.normal(0.0004, 0.01, (n_days, n))
    return pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=idx,
                        columns=[f"S{i}" for i in range(n)])


def ew(mu, cov, window=None):
    return np.full(len(mu), 1 / len(mu))


def first(mu, cov, window=None):
    w = np.zeros(len(mu))
    w[int(np.argmax(mu))] = 1.0
    return w


def test_buy_and_hold_weights_drift_with_prices():
    idx = pd.bdate_range("2021-01-04", periods=3)
    r = pd.DataFrame({"A": [0.0, 0.10, 0.0], "B": [0.0, -0.10, 0.10]}, index=idx)
    out = hold_returns(r, pd.Series({"A": 0.5, "B": 0.5}))
    assert out.iloc[1] == pytest.approx(0.0)
    assert out.iloc[2] == pytest.approx(0.45 * 0.10 / 1.0)  # B is 0.45 of a book worth 1.0


def test_a_delisted_stock_stays_at_its_last_price():
    idx = pd.bdate_range("2021-01-04", periods=3)
    r = pd.DataFrame({"A": [0.0, np.nan, np.nan], "B": [0.0, 0.02, 0.02]}, index=idx)
    out = hold_returns(r, pd.Series({"A": 0.5, "B": 0.5}))
    assert out.iloc[1] == pytest.approx(0.01)


def test_weights_use_only_data_before_each_rebalance():
    px = _prices()
    members = lambda day: list(px.columns)  # noqa: E731
    base = walk_forward(px, members, {"first": first}, lookback=120)
    later = px.copy()
    future = later.index >= "2021-01-01"
    later.loc[future] *= np.random.default_rng(9).uniform(0.5, 2.0, (future.sum(), 6))
    moved = walk_forward(later, members, {"first": first}, lookback=120)
    b, m = base["weights"]["first"], moved["weights"]["first"]
    for day in b:
        if day < pd.Timestamp("2021-01-01"):
            pd.testing.assert_series_equal(b[day], m[day])


def test_returns_start_after_the_first_lookback_and_cover_every_day():
    px = _prices()
    out = walk_forward(px, lambda day: list(px.columns), {"ew": ew}, lookback=120)
    r = out["returns"]["ew"]
    assert r.index[0] > px.index[120] and r.notna().all()
    assert set(out["weights"]["ew"]) <= set(px.index)
