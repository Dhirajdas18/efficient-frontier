"""Walk-forward portfolio test: rebalance monthly on past data only, then hold.

On the first trading day of each month, a strategy turns annualised estimates (mean returns `mu`
and covariance `cov`) and the daily returns behind them, all from the previous `lookback` trading
days, into weights. The portfolio is
held buy-and-hold until the next rebalance, so weights drift with prices. A stock that stops
trading stays at its last price (its value sits idle). Before costs; turnover is recorded.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

TRADING_DAYS = 252
Strategy = Callable[[pd.Series, pd.DataFrame, pd.DataFrame], np.ndarray]


def hold_returns(r: pd.DataFrame, w: pd.Series) -> pd.Series:
    """Daily returns of a buy-and-hold book that starts at weights `w` (missing return = 0)."""
    r = r[w.index].fillna(0.0)
    value = w.to_numpy(dtype=float).copy()
    out = np.empty(len(r))
    for i, row in enumerate(r.to_numpy()):
        total = value.sum()
        out[i] = (value * row).sum() / total
        value *= 1 + row
    return pd.Series(out, index=r.index)


def rebalance_days(index: pd.DatetimeIndex, lookback: int) -> list[pd.Timestamp]:
    firsts = pd.Series(index, index=index).groupby([index.year, index.month]).first()
    return [d for d in firsts if index.get_loc(d) >= lookback]


def walk_forward(prices: pd.DataFrame, members: Callable[[pd.Timestamp], list[str]],
                 strategies: dict[str, Strategy], lookback: int = 756,
                 min_coverage: float = 0.95) -> dict:
    """Run every strategy on the same rebalance dates and universe.

    `members(day)` gives the eligible stocks, using only information before `day`. A member also
    needs prices on at least `min_coverage` of the lookback window and on the day before.
    Returns {"returns": DataFrame of daily returns per strategy, "weights": {name: {day: Series}},
    "info": DataFrame per rebalance with in-sample predicted return and volatility per strategy}.
    """
    r = prices.pct_change(fill_method=None)
    days = rebalance_days(prices.index, lookback)
    rets = {name: [] for name in strategies}
    weights = {name: {} for name in strategies}
    info = []
    for k, day in enumerate(days):
        i = prices.index.get_loc(day)
        window = r.iloc[i - lookback:i]
        names = [s for s in members(day) if s in r.columns
                 and window[s].notna().mean() >= min_coverage and pd.notna(prices[s].iloc[i - 1])]
        if len(names) < 2:
            continue
        mu = window[names].mean() * TRADING_DAYS
        cov = window[names].cov() * TRADING_DAYS
        end = prices.index.get_loc(days[k + 1]) if k + 1 < len(days) else len(prices)
        period = r.iloc[i:end]
        row = {"date": day, "n": len(names)}
        for name, strategy in strategies.items():
            w = pd.Series(np.asarray(strategy(mu, cov, window[names]), dtype=float),
                          index=names)
            weights[name][day] = w
            rets[name].append(hold_returns(period, w))
            row[f"{name}_ret"] = float(w @ mu)
            row[f"{name}_vol"] = float(np.sqrt(w @ cov @ w))
        info.append(row)
    returns = pd.DataFrame({name: pd.concat(v) for name, v in rets.items()})
    return {"returns": returns, "weights": weights, "info": pd.DataFrame(info).set_index("date")}
