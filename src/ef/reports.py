"""README findings, one function per topic: `ef report <topic>` writes charts to out/."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ef import plots
from ef.data import INDEX, SYMBOLS, daily_returns
from ef.frontier import frontier, max_sharpe, min_variance, port_stats

RF = 0.065  # assumed risk-free rate (India 91-day T-bills ran roughly 3-7% over 2013-2026)
TRADING_DAYS = 252
LOOKBACK_YEARS = 3  # long enough for annual estimates, short enough that all 50 have history
PAIR = ["HDFCBANK", "INFY"]


def recent_returns(years: int = LOOKBACK_YEARS) -> pd.DataFrame:
    """Daily returns of today's NIFTY 50 and the index over the last `years` years."""
    from ef.data import DATA_PATH

    px = pd.read_parquet(DATA_PATH)["adj_close"][SYMBOLS + [INDEX]]
    r = daily_returns(px)
    start = r.index[-1] - pd.DateOffset(years=years)
    return r[r.index > start].dropna()


def estimates(r: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Annualised sample mean returns and covariance (simple returns × 252)."""
    return r.mean() * TRADING_DAYS, r.cov() * TRADING_DAYS


def sharpe(ret: float, vol: float, rf: float = RF) -> float:
    return (ret - rf) / vol


def report_frontier(out_dir: Path) -> dict:
    """The efficient frontier of today's NIFTY 50 over the last three years (in-sample)."""
    r = recent_returns()
    mu, cov = estimates(r[SYMBOLS])
    m, c = mu.to_numpy(), cov.to_numpy()
    vols = np.sqrt(np.diag(c))
    nifty = (float(r[INDEX].mean() * TRADING_DAYS), float(r[INDEX].std() * np.sqrt(TRADING_DAYS)))

    # 1. two stocks
    pm, pc = mu[PAIR].to_numpy(), cov.loc[PAIR, PAIR].to_numpy()
    mixes = np.linspace(0, 1, 101)
    curve = np.array([port_stats([1 - a, a], pm, pc) for a in mixes])
    wp = min_variance(pc)
    pr, pv = port_stats(wp, pm, pc)
    corr = float(r[PAIR].corr().iloc[0, 1])
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot(curve[:, 1] * 100, curve[:, 0] * 100, color=plots.SERIES[0])
    for name, (ret, vol) in zip(PAIR, zip(pm, np.sqrt(np.diag(pc)), strict=True), strict=True):
        ax.plot(vol * 100, ret * 100, "o", color=plots.SERIES[0], ms=7)
        ax.annotate(f"100% {name}", (vol * 100, ret * 100), xytext=(8, -4),
                    textcoords="offset points", fontsize=9, color=plots.TEXT_2)
    ax.plot(pv * 100, pr * 100, "o", color=plots.SERIES[1], ms=8)
    ax.annotate(f"{wp[0]:.0%} / {wp[1]:.0%}: lowest risk", (pv * 100, pr * 100), xytext=(8, -4),
                textcoords="offset points", fontsize=9, color=plots.TEXT_2)
    ax.set_xlabel("volatility, % a year")
    ax.set_ylabel("return, % a year")
    ax.set_title(f"Two stocks with correlation {corr:.2f}: the mix is safer than either alone")
    plots.save(fig, out_dir, "frontier_pair")

    # 2. fifty stocks
    pts = frontier(m, c, n=40)
    w_mv, w_ms = min_variance(c), max_sharpe(m, c, RF)
    mv, ms = port_stats(w_mv, m, c), port_stats(w_ms, m, c)
    ew = port_stats(np.full(len(m), 1 / len(m)), m, c)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.scatter(vols * 100, m * 100, s=14, color=plots.MUTED, label="single stocks")
    ax.plot([p["vol"] * 100 for p in pts], [p["ret"] * 100 for p in pts], color=plots.SERIES[0],
            label="efficient frontier (long-only)")
    x = np.linspace(0, max(vols) * 100, 2)
    ax.plot(x, RF * 100 + sharpe(*ms) * x, color=plots.SERIES[0], ls="--", lw=1,
            label="capital market line")
    for (ret, vol), name, color in ((mv, "minimum variance", plots.SERIES[2]),
                                    (ms, "maximum Sharpe", plots.SERIES[1]),
                                    (ew, "equal weight", plots.SERIES[3]),
                                    (nifty, "NIFTY 50 index", plots.TEXT)):
        ax.plot(vol * 100, ret * 100, "o", ms=8, color=color, label=name,
                markeredgecolor=plots.SURFACE)
    ax.set_xlim(0, max(vols) * 105)
    ax.set_xlabel("volatility, % a year")
    ax.set_ylabel("return, % a year")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title("Looking back, the frontier promises far more than the index delivered")
    plots.save(fig, out_dir, "frontier_nifty50")

    # 3. what the two optimal portfolios hold
    top = pd.DataFrame({"max Sharpe": w_ms, "min variance": w_mv}, index=SYMBOLS)
    top = top[(top > 0.02).any(axis=1)].sort_values("max Sharpe")
    fig, ax = plt.subplots(figsize=(9, 5.2))
    y = np.arange(len(top))
    ax.barh(y + 0.2, top["max Sharpe"] * 100, 0.38, color=plots.SERIES[1], label="maximum Sharpe")
    ax.barh(y - 0.2, top["min variance"] * 100, 0.38, color=plots.SERIES[2],
            label="minimum variance")
    ax.set_yticks(y, top.index, fontsize=8)
    ax.set_xlabel("weight, %")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")
    ax.set_title("Maximum Sharpe piles into past winners; minimum variance into defensives")
    plots.save(fig, out_dir, "frontier_weights")

    held = lambda w: int((w > 0.01).sum())  # noqa: E731
    return {
        "window": f"{r.index[0]:%Y-%m-%d} to {r.index[-1]:%Y-%m-%d} ({len(r)} days)",
        "average stock vol": f"{vols.mean():.1%}",
        "NIFTY ret / vol / Sharpe": (f"{nifty[0]:.1%}", f"{nifty[1]:.1%}",
                                     round(sharpe(*nifty), 2)),
        "equal weight ret / vol / Sharpe": (f"{ew[0]:.1%}", f"{ew[1]:.1%}", round(sharpe(*ew), 2)),
        "min variance ret / vol / stocks >1%": (f"{mv[0]:.1%}", f"{mv[1]:.1%}", held(w_mv)),
        "max Sharpe ret / vol / Sharpe / stocks >1%": (f"{ms[0]:.1%}", f"{ms[1]:.1%}",
                                                        round(sharpe(*ms), 2), held(w_ms)),
        "max Sharpe top 5": {k: f"{v:.1%}" for k, v in
                             pd.Series(w_ms, SYMBOLS).nlargest(5).items()},
        "min variance top 5": {k: f"{v:.1%}" for k, v in
                               pd.Series(w_mv, SYMBOLS).nlargest(5).items()},
        "pair": f"{PAIR} corr {corr:.2f}, vols {np.sqrt(np.diag(pc)).round(3).tolist()}, "
                f"lowest-risk mix {wp.round(2).tolist()} vol {pv:.1%}",
    }


REPORTS = {"frontier": report_frontier}
