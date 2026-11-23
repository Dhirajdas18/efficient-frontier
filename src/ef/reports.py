"""README findings, one function per topic: `ef report <topic>` writes charts to out/."""

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ef import plots
from ef.data import INDEX, SYMBOLS, daily_returns
from ef.frontier import frontier, max_sharpe, min_variance, port_stats, risk_parity
from ef.universe import load_nifty

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


ESTIMATION = Path("docs/data/estimation_monthly.csv")  # monthly strategy returns, committed
WINDOW = 756  # three years of trading days


def _equal(mu, cov, window):
    return np.full(len(mu), 1 / len(mu))


def _min_var(mu, cov, window):
    return min_variance(cov.to_numpy())


def _max_sharpe(mu, cov, window):
    return max_sharpe(mu.to_numpy(), cov.to_numpy(), RF)


def _resampled(mu, cov, window):
    from ef.frontier import resampled_max_sharpe

    return resampled_max_sharpe(window.fillna(0.0).to_numpy(), RF, n_boot=20, seed=0)


def lake_walk(strategies: dict, lookback: int = WINDOW) -> tuple[dict, pd.DataFrame]:
    """Walk forward over the point-in-time universe from the lake: the 50 most-traded stocks
    among those with F&O contracts the day before each rebalance."""
    from ef.universe import load_fno, load_lake, members_at
    from ef.walkforward import walk_forward

    px, turnover = load_lake()
    fno = load_fno()
    out = walk_forward(px, lambda day: members_at(turnover, day, 50, eligible=fno), strategies,
                       lookback)
    return out, px


def stats(r: pd.Series, rf: float = RF) -> dict:
    """Compound return, volatility and Sharpe of a return series, annualised by calendar time:
    observations a year = (n - 1) / years between the first and last date, so NSE's ~247
    trading days or a weekday calendar are both handled."""
    r = r.dropna()
    span = (r.index[-1] - r.index[0]).days / 365.25
    per_year = (len(r) - 1) / span
    vol = float(r.std() * np.sqrt(per_year))
    cagr = float((1 + r).prod() ** (per_year / len(r)) - 1)
    return {"cagr": cagr, "vol": vol, "sharpe": float((r.mean() * per_year - rf) / vol),
            "mean": float(r.mean() * per_year)}


def report_estimation(out_dir: Path) -> dict:
    """Estimation error: portfolios picked on the past three years, scored on the next month."""
    from scipy.stats import spearmanr

    strategies = {"equal weight": _equal, "min variance": _min_var, "max Sharpe": _max_sharpe,
                  "resampled max Sharpe": _resampled}
    out, px = lake_walk(strategies)
    rets, info = out["returns"], out["info"]
    nifty = load_nifty().pct_change()
    rets = rets.assign(NIFTY=nifty.reindex(rets.index))
    monthly = rets.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly.index.name = "date"
    monthly.to_csv(ESTIMATION, float_format="%.6f")
    real = {k: stats(rets[k]) for k in rets}
    pred = {k: {"ret": float(info[f"{k}_ret"].mean()), "vol": float(info[f"{k}_vol"].mean()),
                "sharpe": float(((info[f"{k}_ret"] - RF) / info[f"{k}_vol"]).mean())}
            for k in strategies}

    # does a stock's past three-year return rank next month's? (cross-sectional rank IC)
    r_all = px.pct_change(fill_method=None)
    days = list(info.index)
    ics = []
    for a, b in zip(days, days[1:], strict=False):
        w = out["weights"]["equal weight"][a]
        i = px.index.get_loc(a)
        past = r_all.iloc[i - WINDOW:i][w.index].mean()
        nxt = (1 + r_all.loc[a:b].iloc[:-1][w.index].fillna(0)).prod() - 1
        ics.append(spearmanr(past, nxt).statistic)
    ics = np.array(ics)

    names = list(strategies)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4.6))
    xs = np.arange(len(names))
    for ax, key, label in ((a1, "sharpe", "Sharpe ratio"), (a2, "vol", "volatility, %")):
        k = 100 if key == "vol" else 1
        ax.bar(xs - 0.2, [pred[n][key] * k for n in names], 0.38, color=plots.MUTED,
               label="promised (in-sample)")
        ax.bar(xs + 0.2, [real[n][key] * k for n in names], 0.38, color=plots.SERIES[0],
               label="delivered (next month)")
        ax.set_xticks(xs, [n.replace(" ", "\n", 1) for n in names], fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="normal", color=plots.TEXT_2)
        ax.grid(axis="x", visible=False)
    a1.set_ylim(0, max(pred[n]["sharpe"] for n in names) * 1.3)
    a1.legend(loc="upper left", fontsize=8)
    fig.suptitle("Risk forecasts held up; return forecasts collapsed", x=0.06, ha="left",
                 fontsize=13, fontweight="semibold", color=plots.TEXT)
    plots.save(fig, out_dir, "estimation_promised")

    fig, ax = plt.subplots(figsize=(9, 4.6))
    colors = dict(zip([*names, "NIFTY"], [plots.SERIES[3], plots.SERIES[2], plots.SERIES[1],
                                          plots.SERIES[6], plots.TEXT], strict=True))
    for k in [*names, "NIFTY"]:
        g = (1 + rets[k]).cumprod()
        ax.plot(g.index, g, color=colors[k], lw=2 if k != "NIFTY" else 1.2,
                label=f"{k}: {real[k]['cagr']:.1%} a year")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator([0.75, 1, 1.5, 2, 3, 4]))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"₹{v:g}"))
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_ylabel("growth of ₹1 (log scale, before costs)")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title("Out of sample, every portfolio ended near the index, far from its promise")
    plots.save(fig, out_dir, "estimation_growth")

    last = days[-1]
    i = px.index.get_loc(last)
    w_last = out["weights"]["max Sharpe"][last]
    window = r_all.iloc[i - WINDOW:i][w_last.index].fillna(0.0).to_numpy()
    rng = np.random.default_rng(0)
    boots = []
    for _ in range(200):
        sample = window[rng.integers(0, len(window), len(window))]
        boots.append(max_sharpe(sample.mean(0) * TRADING_DAYS, np.cov(sample.T) * TRADING_DAYS, RF))
    boots = pd.DataFrame(boots, columns=w_last.index)
    top = w_last.nlargest(8).index
    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(top))[::-1]
    lo, hi = boots[top].quantile(0.1) * 100, boots[top].quantile(0.9) * 100
    ax.hlines(y, lo, hi, color=plots.SERIES[0], lw=6, alpha=0.35, label="10–90% of resamples")
    ax.plot(w_last[top] * 100, y, "o", color=plots.SERIES[1], label="weight on the actual data")
    ax.set_yticks(y, top, fontsize=9)
    ax.set_xlabel("max-Sharpe weight, %")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Resample the same three years and the {last:%b %Y} weights swing wildly")
    plots.save(fig, out_dir, "estimation_bootstrap")

    held = {k: float(np.median([(w > 0.01).sum() for w in out["weights"][k].values()]))
            for k in strategies}
    window_df = r_all.iloc[i - WINDOW:i][w_last.index]
    se = float((window_df.std() * np.sqrt(TRADING_DAYS) / np.sqrt(WINDOW / TRADING_DAYS))
               .median())
    return {
        "rebalances": f"{len(days)} ({days[0]:%Y-%m} to {days[-1]:%Y-%m}); "
                      f"median members {int(info['n'].median())}",
        "promised (ret, vol, sharpe)": {k: tuple(round(v, 3) for v in pred[k].values())
                                        for k in pred},
        "delivered (cagr, vol, sharpe, arithmetic mean)": {
            k: tuple(round(v, 3) for v in real[k].values()) for k in real},
        "stocks held >1% (median)": held,
        "past-3y-return rank IC on next month: mean / t / share>0":
            (round(float(ics.mean()), 3), round(float(ics.mean() / ics.std() * np.sqrt(len(ics))),
                                                2), round(float((ics > 0).mean()), 2)),
        "std error of a 3y annual mean return, median stock": f"{se:.1%}",
        "bootstrap: top weight 10-90%": {s: f"{lo[s]:.0f}-{hi[s]:.0f}% (actual "
                                            f"{w_last[s]:.0%})" for s in top[:4]},
        "bootstrap: share of resamples where each top-8 stock gets 0":
            {s: round(float((boots[s] < 0.001).mean()), 2) for s in top},
    }


SHRINKAGE = Path("docs/data/covariance_shrinkage.csv")  # Ledoit-Wolf intensity per rebalance


def _min_var_with(estimator, long_only: bool, log: list):
    """Minimum variance from a covariance estimator on the window's daily returns; records the
    portfolio's predicted volatility."""
    def strategy(mu, cov, window):
        c = estimator(window.fillna(0.0).to_numpy())
        if long_only:
            w = min_variance(c)
        else:
            w = np.linalg.solve(c, np.ones(len(c)))  # unconstrained: Σ⁻¹1 / 1'Σ⁻¹1
            w /= w.sum()
        log.append(float(np.sqrt(w @ c @ w)))
        return w
    return strategy


def report_covariance(out_dir: Path) -> dict:
    """Covariance estimators judged by the next month's realised risk of minimum variance."""
    from ef.covariance import ewma_cov, ledoit_wolf_cc, sample_cov

    shrinks: dict[int, list] = {}
    estimators = {"sample": sample_cov, "Ledoit-Wolf": ledoit_wolf_cc,
                  "EWMA 63d": lambda x: ewma_cov(x, 63)}
    results, ratio, gross, dates = {}, {}, {}, {}
    for lb in (WINDOW, TRADING_DAYS):
        shrinks[lb] = []

        def lw_logged(x, lb=lb):
            c, k = ledoit_wolf_cc(x, return_shrinkage=True)
            shrinks[lb].append(k)
            return c

        logs = {}
        strategies = {}
        for name, est in estimators.items():
            for long_only in (True, False):
                key = f"{name}, {'long-only' if long_only else 'shorting'}"
                logs[key] = []
                strategies[key] = _min_var_with(lw_logged if name == "Ledoit-Wolf" else est,
                                                long_only, logs[key])
        out, _ = lake_walk(strategies, lookback=lb)
        dates[lb] = list(out["info"].index)
        rets = out["returns"][out["returns"].index >= "2016-02-01"]
        for key in strategies:
            r = out["returns"][key]
            month_vol = r.groupby(pd.Grouper(freq="ME")).std() * np.sqrt(TRADING_DAYS)
            pred = np.array(logs[key][: len(month_vol)])
            keep = month_vol.index >= "2016-02-01"  # same months for both look-backs
            month_vol, pred = month_vol[keep], pred[keep]
            results[(lb, key)] = stats(rets[key])["vol"]
            ratio[(lb, key)] = float(np.median(month_vol.to_numpy() / pred))
            gross[(lb, key)] = float(np.median([w.abs().sum() for d, w in
                                                out["weights"][key].items()
                                                if d >= pd.Timestamp("2016-02-01")]))
    labels = list(estimators)
    yrs = {WINDOW: "3 years", TRADING_DAYS: "1 year"}

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.6), sharey=True)
    xs = np.arange(len(labels))
    for ax, lb in zip(axes, (WINDOW, TRADING_DAYS), strict=True):
        lo = [results[(lb, f"{n}, long-only")] * 100 for n in labels]
        sh = [results[(lb, f"{n}, shorting")] * 100 for n in labels]
        ax.bar(xs - 0.2, lo, 0.38, color=plots.SERIES[0], label="long-only")
        ax.bar(xs + 0.2, sh, 0.38, color=plots.SERIES[1], label="shorting allowed")
        for i in range(len(labels)):
            ax.text(i - 0.2, lo[i] + 0.1, f"{lo[i]:.1f}", ha="center", fontsize=8)
            ax.text(i + 0.2, sh[i] + 0.1, f"{sh[i]:.1f}", ha="center", fontsize=8)
        ax.set_xticks(xs, labels, fontsize=9)
        ax.set_ylim(0, 17)
        ax.grid(axis="x", visible=False)
        ax.set_title(f"estimated from {yrs[lb]}", fontsize=10, fontweight="normal",
                     color=plots.TEXT_2)
    axes[0].set_ylabel("realised volatility of minimum variance, %")
    axes[1].legend(loc="upper right", fontsize=8)
    fig.suptitle("Long-only, the estimator barely mattered; with shorting, shrinkage helped",
                 x=0.06, ha="left", fontsize=13, fontweight="semibold", color=plots.TEXT)
    plots.save(fig, out_dir, "covariance_realised")

    fig, ax = plt.subplots(figsize=(9, 4.6))
    keys = [f"{n}, {m}" for m in ("long-only", "shorting") for n in labels]
    xs = np.arange(len(keys))
    vals = [ratio[(TRADING_DAYS, k)] for k in keys]
    ax.bar(xs, vals, 0.55, color=[plots.SERIES[0]] * 3 + [plots.SERIES[1]] * 3)
    ax.axhline(1, color=plots.TEXT_2, lw=1, ls="--")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.04, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_xticks(xs, [k.replace(", ", "\n") for k in keys], fontsize=8)
    ax.set_ylabel("realised ÷ predicted volatility (median month)")
    ax.grid(axis="x", visible=False)
    ax.set_title("Free to short, the optimiser trusted its own risk estimate too much")
    plots.save(fig, out_dir, "covariance_forecast")

    fig, ax = plt.subplots(figsize=(9, 4.6))
    for lb, color in ((WINDOW, plots.SERIES[0]), (TRADING_DAYS, plots.SERIES[1])):
        k = shrinks[lb][::2]  # the long-only and shorting runs estimate the same windows
        ax.plot(dates[lb], np.array(k) * 100, color=color, label=f"estimated from {yrs[lb]}")
    pd.DataFrame({yrs[lb]: pd.Series(shrinks[lb][::2], index=dates[lb]) for lb in dates}) \
        .rename_axis("date").to_csv(SHRINKAGE, float_format="%.4f")
    ax.set_ylabel("Ledoit-Wolf shrinkage toward constant correlation, %")
    ax.legend(loc="upper right")
    ax.set_title("How far Ledoit-Wolf pulled the sample estimate toward its target")
    plots.save(fig, out_dir, "covariance_shrinkage")

    return {
        "realised vol (lookback, strategy)": {f"{yrs[lb]} | {k}": f"{v:.1%}"
                                              for (lb, k), v in results.items()},
        "realised/predicted (median month)": {f"{yrs[lb]} | {k}": round(v, 2)
                                              for (lb, k), v in ratio.items()},
        "gross exposure median": {f"{yrs[lb]} | {k}": round(v, 2)
                                  for (lb, k), v in gross.items() if "shorting" in k},
        "shrinkage median (3y, 1y)": (round(float(np.median(shrinks[WINDOW])), 2),
                                      round(float(np.median(shrinks[TRADING_DAYS])), 2)),
    }


CAPITAL = 1_000_000.0  # ₹10 lakh: the DP charge is per stock sold, so size matters
CONTEST = Path("docs/data/contest_monthly.csv")  # monthly net returns, committed for the site


def _inverse_vol(days: int | None):
    def strategy(mu, cov, window):
        v = (window.iloc[-days:] if days else window).std().fillna(window.std())
        return ((1 / v) / (1 / v).sum()).to_numpy()
    return strategy


def _lw(window):
    from ef.covariance import ledoit_wolf_cc

    return ledoit_wolf_cc(window.fillna(0.0).to_numpy())


CONTENDERS = {
    "equal weight": _equal,
    "inverse vol (20 days)": _inverse_vol(20),
    "inverse vol (1 year)": _inverse_vol(TRADING_DAYS),
    "risk parity": lambda mu, cov, w: risk_parity(_lw(w)),
    "min variance": lambda mu, cov, w: min_variance(_lw(w)),
    "max Sharpe": _max_sharpe,
}


def report_contest(out_dir: Path) -> dict:
    """Walk-forward contest after Indian delivery costs on a ₹10 lakh portfolio."""
    from ef.costs import RATES, trade_cost
    from ef.universe import load_fno, load_lake, members_at
    from ef.walkforward import walk_forward

    px, turnover = load_lake()
    fno = load_fno()
    members = lambda day: members_at(turnover, day, 50, eligible=fno)  # noqa: E731
    parts = {"all costs": RATES, "no DP charge": {**RATES, "dp_per_sell": 0.0},
             "no STT": {**RATES, "stt": 0.0}, "no slippage": {**RATES, "slippage": 0.0},
             "none": None}
    runs = {}
    for label, rates in parts.items():
        cost = None if rates is None else (
            lambda b, s_, n, g, r=rates: trade_cost(b, s_, n, CAPITAL * g, r))
        runs[label] = walk_forward(px, members, CONTENDERS, WINDOW, cost=cost)
    net, gross = runs["all costs"], runs["none"]
    nifty = load_nifty().pct_change()
    rets = net["returns"].assign(NIFTY=nifty.reindex(net["returns"].index))
    monthly = rets.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly.index.name = "date"
    monthly.to_csv(CONTEST, float_format="%.6f")

    names = list(CONTENDERS)
    dd = lambda r: float(((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min())  # noqa: E731
    on = lambda run, k: run["returns"][k].reindex(rets.index)  # noqa: E731  same days for all
    table = {k: {**stats(rets[k]), "gross": stats(on(gross, k))["cagr"],
                 "dd": dd(rets[k]), "turnover": float(net["turnover"][k].median())}
             for k in names}
    table["NIFTY"] = {**stats(rets["NIFTY"]), "dd": dd(rets["NIFTY"])}
    cost_part = {}
    for k in names:
        total = table[k]["gross"] - table[k]["cagr"]
        cost_part[k] = {lab.replace("no ", ""): stats(on(runs[lab], k))["cagr"]
                        - table[k]["cagr"] for lab in ("no STT", "no slippage", "no DP charge")}
        cost_part[k]["total"] = total
    base = monthly["inverse vol (20 days)"]
    tstat = {k: float((monthly[k] - base).mean() / (monthly[k] - base).std()
                      * np.sqrt(len(base))) for k in names if k != "inverse vol (20 days)"}
    yearly_vol = rets.groupby(rets.index.year).std() * np.sqrt(TRADING_DAYS)
    mv_lower = int((yearly_vol["min variance"] < yearly_vol["inverse vol (20 days)"]).sum())

    colors = dict(zip([*names, "NIFTY"], [plots.SERIES[3], plots.SERIES[0], plots.SERIES[4],
                                          plots.SERIES[6], plots.SERIES[2], plots.SERIES[1],
                                          plots.TEXT], strict=True))
    fig, ax = plt.subplots(figsize=(9, 5))
    for k in [*names, "NIFTY"]:
        t = table[k]
        ax.plot(t["vol"] * 100, t["cagr"] * 100, "o", ms=10, color=colors[k],
                markeredgecolor=plots.SURFACE)
        dy = {"inverse vol (1 year)": 5, "inverse vol (20 days)": -9}.get(k, -3)
        ax.annotate(f"{k}  (worst fall {t['dd']:.0%})", (t["vol"] * 100, t["cagr"] * 100),
                    xytext=(9, dy), textcoords="offset points", fontsize=8, color=plots.TEXT_2)
    ax.set_xlim(12, 27)
    ax.set_ylim(9, 13.5)
    ax.set_xlabel("volatility, % a year")
    ax.set_ylabel("return after costs, % a year")
    ax.set_title("After costs the returns bunch together; the risk doesn't")
    plots.save(fig, out_dir, "contest_risk_return")

    fig, ax = plt.subplots(figsize=(9, 4.6))
    for k in ("equal weight", "inverse vol (20 days)", "min variance", "NIFTY"):
        g = (1 + rets[k]).cumprod()
        ax.plot(g.index, (g / g.cummax() - 1) * 100, color=colors[k], label=k,
                lw=1.2 if k == "NIFTY" else 1.8)
    ax.set_ylabel("fall from previous peak, %")
    ax.legend(loc="lower left", fontsize=9)
    ax.set_title("Minimum variance fell least in 2020, but sat furthest below its peak in 2026")
    plots.save(fig, out_dir, "contest_drawdown")

    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(names))[::-1]
    left = np.zeros(len(names))
    for part, color in (("STT", plots.SERIES[1]), ("slippage", plots.SERIES[3]),
                        ("DP charge", plots.SERIES[6])):
        vals = np.array([cost_part[k][part] * 100 for k in names])
        ax.barh(y, vals, 0.55, left=left, color=color, label=part)
        left += vals
    for i, k in enumerate(names):
        ax.text(left[i] + 0.02, y[i], f"{cost_part[k]['total']:.2%} a year  "
                f"(turnover {table[k]['turnover']:.0%} a month)", va="center", fontsize=8)
    ax.set_yticks(y, names, fontsize=9)
    ax.set_xlim(0, left.max() * 1.9)
    ax.set_xlabel("cost, % a year (₹10 lakh portfolio)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title("Twenty-day inverse volatility trades most and pays most")
    plots.save(fig, out_dir, "contest_costs")

    return {
        "net (cagr, vol, sharpe, worst fall)": {k: (f"{t['cagr']:.1%}", f"{t['vol']:.1%}",
                                                    round(t["sharpe"], 2), f"{t['dd']:.0%}")
                                                for k, t in table.items()},
        "gross cagr": {k: f"{table[k]['gross']:.1%}" for k in names},
        "turnover a month (median)": {k: f"{table[k]['turnover']:.1%}" for k in names},
        "cost a year (STT, slippage, DP, total)": {
            k: tuple(f"{cost_part[k][p]:.2%}" for p in ("STT", "slippage", "DP charge", "total"))
            for k in names},
        "monthly return diff vs inverse vol (20d), t": {k: round(v, 2) for k, v in tstat.items()},
        "years min variance had lower vol than inverse vol (20d)":
            f"{mv_lower} of {len(yearly_vol)}",
    }


SECTORS = Path("docs/data/sectors.csv")  # NSE industry per stock that ever entered the universe
STOCK_CAP, SECTOR_CAP = 0.15, 0.30  # the reference model's caps (MODEL_SPEC §7.3)
PENALTIES = (0.0005, 0.002, 0.005)  # turnover penalty, annual-variance units per unit traded
CONSTRAINTS = Path("docs/data/constraints_monthly.csv")  # monthly net returns, for the site


def _sectors(index) -> np.ndarray:
    sec = pd.read_csv(SECTORS).set_index("symbol")["industry"]
    return sec.reindex(index).fillna("unknown").to_numpy()


def _constrained():
    def mv(capped):
        def f(mu, cov, w):
            if not capped:
                return min_variance(_lw(w))
            return min_variance(_lw(w), (0.0, STOCK_CAP), _sectors(mu.index), SECTOR_CAP)
        return f

    def ms(capped):
        def f(mu, cov, w):
            if not capped:
                return max_sharpe(mu.to_numpy(), cov.to_numpy(), RF)
            return max_sharpe(mu.to_numpy(), cov.to_numpy(), RF, (0.0, STOCK_CAP),
                              _sectors(mu.index), SECTOR_CAP)
        return f

    def penalised(lam):
        from ef.frontier import min_variance_penalised

        def f(mu, cov, w, prev):
            return min_variance_penalised(_lw(w), prev.to_numpy(), lam, (0.0, STOCK_CAP),
                                          _sectors(mu.index), SECTOR_CAP)
        f.needs_prev = True
        return f

    out = {"max Sharpe": ms(False), "max Sharpe, capped": ms(True),
           "min variance": mv(False), "min variance, capped": mv(True)}
    out |= {f"min variance, capped, penalty {lam:g}": penalised(lam) for lam in PENALTIES}
    return out | {"inverse vol (1 year)": _inverse_vol(TRADING_DAYS)}


def report_constraints(out_dir: Path) -> dict:
    """Stock and sector caps and a turnover penalty, after costs on ₹10 lakh."""
    from ef.costs import trade_cost
    from ef.universe import load_fno, load_lake, members_at
    from ef.walkforward import walk_forward

    px, turnover = load_lake()
    fno = load_fno()
    members = lambda day: members_at(turnover, day, 50, eligible=fno)  # noqa: E731
    strategies = _constrained()
    net = walk_forward(px, members, strategies, WINDOW,
                       cost=lambda b, s_, n, g: trade_cost(b, s_, n, CAPITAL * g))
    gross = walk_forward(px, members, strategies, WINDOW)
    rets = net["returns"]
    dd = lambda r: float(((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min())  # noqa: E731

    def biggest_sector(w):
        return float(w.groupby(_sectors(w.index)).sum().max())

    table = {}
    for k in strategies:
        st = stats(rets[k])
        ws = net["weights"][k].values()
        table[k] = {**st, "dd": dd(rets[k]), "turnover": float(net["turnover"][k].median()),
                    "cost": stats(gross["returns"][k])["cagr"] - st["cagr"],
                    "max stock": float(np.median([w.max() for w in ws])),
                    "max sector": float(np.median([biggest_sector(w) for w in ws]))}
    monthly = rets.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    keep = ["max Sharpe", "max Sharpe, capped", "min variance, capped",
            f"min variance, capped, penalty {PENALTIES[-1]:g}"]
    monthly[keep].rename_axis("date").to_csv(CONSTRAINTS, float_format="%.6f")
    diff = monthly["max Sharpe, capped"] - monthly["max Sharpe"]
    t_ms = float(diff.mean() / diff.std() * np.sqrt(len(diff)))

    pairs = [("max Sharpe", "max Sharpe, capped"), ("min variance", "min variance, capped")]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.6))
    for ax, (key, label) in zip(axes, (("vol", "volatility, %"), ("dd", "worst fall, %")),
                                strict=True):
        xs = np.arange(len(pairs))
        a = [abs(table[p[0]][key]) * 100 for p in pairs]
        b = [abs(table[p[1]][key]) * 100 for p in pairs]
        ax.bar(xs - 0.2, a, 0.38, color=plots.MUTED, label="uncapped")
        ax.bar(xs + 0.2, b, 0.38, color=plots.SERIES[0], label="capped (15% stock, 30% sector)")
        for i in range(len(pairs)):
            ax.text(i - 0.2, a[i] + 0.4, f"{a[i]:.0f}", ha="center", fontsize=9)
            ax.text(i + 0.2, b[i] + 0.4, f"{b[i]:.0f}", ha="center", fontsize=9)
        ax.set_xticks(xs, ["maximum Sharpe", "minimum variance"])
        ax.set_title(label, fontsize=10, fontweight="normal", color=plots.TEXT_2)
        ax.grid(axis="x", visible=False)
    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle("Caps tamed maximum Sharpe; minimum variance barely needed them", x=0.06,
                 ha="left", fontsize=13, fontweight="semibold", color=plots.TEXT)
    plots.save(fig, out_dir, "constraints_caps")

    keys = ["min variance, capped"] + [f"min variance, capped, penalty {lam:g}"
                                       for lam in PENALTIES]
    labels = ["no penalty"] + [f"penalty {lam:g}" for lam in PENALTIES]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    xs = np.arange(len(keys))
    turn = [table[k]["turnover"] * 100 for k in keys]
    ax.bar(xs, turn, 0.55, color=plots.SERIES[0])
    for i, k in enumerate(keys):
        ax.text(i, turn[i] + 0.15, f"cost {table[k]['cost']:.2%}/yr\nvolatility "
                f"{table[k]['vol']:.1%}", ha="center", va="bottom", fontsize=8,
                color=plots.TEXT_2)
    ax.set_xticks(xs, labels)
    ax.set_ylim(0, max(turn) * 1.45)
    ax.set_ylabel("turnover a month, % (median)")
    ax.grid(axis="x", visible=False)
    ax.set_title("A turnover penalty cut trading by three quarters at the same risk")
    plots.save(fig, out_dir, "constraints_penalty")

    avg = {}
    for k in ("inverse vol (1 year)", "min variance", "max Sharpe"):
        frames = [w.groupby(_sectors(w.index)).sum() for w in net["weights"][k].values()]
        avg[k] = pd.concat(frames, axis=1).fillna(0).mean(axis=1)
    avg = pd.DataFrame(avg).fillna(0)
    top = avg.max(axis=1).nlargest(7).index
    avg = pd.concat([avg.loc[top], avg.drop(top).sum().to_frame("other").T])
    fig, ax = plt.subplots(figsize=(9, 4.6))
    left = np.zeros(avg.shape[1])
    y = np.arange(avg.shape[1])[::-1]
    palette = [*plots.SERIES[:7], plots.MUTED]
    for color, (sector, row) in zip(palette, avg.iterrows(), strict=True):
        ax.barh(y, row.to_numpy() * 100, 0.55, left=left, color=color, label=sector,
                edgecolor=plots.SURFACE, lw=1)
        left += row.to_numpy() * 100
    ax.set_yticks(y, avg.columns)
    ax.set_xlim(0, 100)
    ax.set_xlabel("average weight, % (uncapped)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=4, fontsize=8, frameon=False)
    ax.set_title("Each optimiser leans on different sectors")
    plots.save(fig, out_dir, "constraints_sectors")

    return {
        "net (cagr, vol, worst fall, turnover, cost/yr, median max stock, median max sector)": {
            k: (f"{t['cagr']:.1%}", f"{t['vol']:.1%}", f"{t['dd']:.0%}", f"{t['turnover']:.1%}",
                f"{t['cost']:.2%}", f"{t['max stock']:.0%}", f"{t['max sector']:.0%}")
            for k, t in table.items()},
        "max Sharpe capped - uncapped, monthly t": round(t_ms, 2),
        "average sector weights": {k: {s: f"{v:.0%}" for s, v in avg[k].items() if v >= 0.05}
                                   for k in avg.columns},
    }


DELTA, TAU = 2.5, 0.05  # risk aversion and prior uncertainty (He & Litterman's usual values)
BL_MONTHLY = Path("docs/data/black_litterman_monthly.csv")


def _bl_strategy(log: list):
    from ef.black_litterman import implied_returns, momentum_view, posterior
    from ef.frontier import max_utility

    def strategy(mu, cov, window):
        c = _lw(window)
        prior = np.full(len(mu), 1 / len(mu))
        pi = implied_returns(c, prior, DELTA)
        p, q, omega = momentum_view(window)
        post, cov_bl = posterior(pi, c, p.to_numpy()[None, :], np.array([q]),
                                 np.array([[omega]]), TAU)
        view_pi, view_post = float(p @ pi), float(p @ post)
        log.append({"q": q, "omega": omega, "prior view": view_pi, "posterior view": view_post,
                    "adopted": (view_post - view_pi) / (q - view_pi) if q != view_pi else 0.0,
                    "sample": mu, "pi": pd.Series(pi, mu.index),
                    "post": pd.Series(post, mu.index)})
        return max_utility(post, cov_bl, DELTA, (0.0, STOCK_CAP), _sectors(mu.index),
                           SECTOR_CAP)
    return strategy


def _momentum_top(mu, cov, window, top: int = 10):
    mom = np.log1p(window.fillna(0.0)).iloc[-252:-21].sum()
    w = pd.Series(0.0, index=mu.index)
    w[mom.nlargest(top).index] = 1 / top
    return w.to_numpy()


def report_black_litterman(out_dir: Path) -> dict:
    """Black-Litterman: equal-weight prior plus a momentum view, after costs on ₹10 lakh."""
    from ef.costs import trade_cost
    from ef.universe import load_fno, load_lake, members_at
    from ef.walkforward import walk_forward

    log: list = []
    strategies = {
        "equal weight (the prior)": _equal,
        "Black-Litterman + momentum view": _bl_strategy(log),
        "momentum, top 10": _momentum_top,
        "max Sharpe on sample means, capped": lambda mu, cov, w: max_sharpe(
            mu.to_numpy(), cov.to_numpy(), RF, (0.0, STOCK_CAP), _sectors(mu.index), SECTOR_CAP),
    }
    px, turnover = load_lake()
    fno = load_fno()
    out = walk_forward(px, lambda day: members_at(turnover, day, 50, eligible=fno), strategies,
                       WINDOW, cost=lambda b, s_, n, g: trade_cost(b, s_, n, CAPITAL * g))
    nifty = load_nifty().pct_change()
    rets = out["returns"].assign(NIFTY=nifty.reindex(out["returns"].index))
    monthly = rets.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly.rename_axis("date").to_csv(BL_MONTHLY, float_format="%.6f")
    dd = lambda r: float(((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min())  # noqa: E731
    table = {k: {**stats(rets[k]), "dd": dd(rets[k]),
                 "turnover": float(out["turnover"][k].median()) if k in out["turnover"] else 0}
             for k in rets}
    base = monthly["equal weight (the prior)"]
    tstat = {k: float((monthly[k] - base).mean() / (monthly[k] - base).std()
                      * np.sqrt(len(base))) for k in strategies if k != "equal weight (the prior)"}
    days = list(out["info"].index)
    lg = pd.DataFrame([{k: v for k, v in e.items() if k not in ("sample", "pi", "post")}
                       for e in log], index=days)

    from scipy.stats import spearmanr

    r_all = px.pct_change(fill_method=None)
    ic, spread = [], []
    for a, b in zip(days, days[1:], strict=False):
        names = out["weights"]["equal weight (the prior)"][a].index
        i = px.index.get_loc(a)
        mom = np.log1p(r_all.iloc[i - 252:i - 21][names].fillna(0.0)).sum()
        fwd = (1 + r_all.loc[a:b].iloc[:-1][names].fillna(0.0)).prod() - 1
        ic.append(spearmanr(mom, fwd).statistic)
        spread.append(fwd[mom.nlargest(10).index].mean() - fwd[mom.nsmallest(10).index].mean())
    ic, spread = np.array(ic), np.array(spread)
    tt = lambda x: float(x.mean() / x.std() * np.sqrt(len(x)))  # noqa: E731

    last = log[-1]
    order = last["sample"].sort_values().index
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = np.arange(len(order))
    ax.plot(x, last["sample"][order] * 100, "o", ms=4, color=plots.MUTED,
            label="sample mean (past 3 years)")
    ax.plot(x, last["pi"][order] * 100, color=plots.SERIES[0], lw=6, alpha=0.35,
            label="prior: implied by equal weight")
    ax.plot(x, last["post"][order] * 100, color=plots.SERIES[1], lw=1.6,
            label="posterior: prior + momentum view (almost on top of it)")
    ax.axhline(0, color=plots.TEXT_2, lw=0.8)
    ax.set_xticks([])
    ax.set_xlabel(f"the {len(order)} stocks, sorted by past return ({days[-1]:%b %Y})")
    ax.set_ylabel("expected return, % a year")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title("Black-Litterman's inputs are calm where sample means are wild")
    plots.save(fig, out_dir, "bl_returns")

    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot(lg.index, lg["q"] * 100, color=plots.MUTED, label="view: momentum spread, past 3 years")
    ax.plot(lg.index, lg["posterior view"] * 100, color=plots.SERIES[1],
            label="what the posterior kept")
    ax.axhline(0, color=plots.TEXT_2, lw=0.8)
    ax.set_ylabel("top-10 minus bottom-10 return, % a year")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title("Black-Litterman kept only a fraction of each month's noisy view")
    plots.save(fig, out_dir, "bl_view")

    names = [k for k in rets if k != "NIFTY"]
    colors = dict(zip([*names, "NIFTY"], [plots.SERIES[3], plots.SERIES[1], plots.SERIES[6],
                                          plots.MUTED, plots.TEXT], strict=True))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for k in [*names, "NIFTY"]:
        g = (1 + rets[k]).cumprod()
        ax.plot(g.index, g, color=colors[k], lw=1.2 if k == "NIFTY" else 1.8,
                label=f"{k}: {table[k]['cagr']:.1%}")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator([0.75, 1, 1.5, 2, 3, 4]))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"₹{v:g}"))
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_ylabel("growth of ₹1 after costs (log scale)")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("A weak view, used with stated confidence, changed little")
    plots.save(fig, out_dir, "bl_growth")

    return {
        "net (cagr, vol, sharpe, worst fall, turnover)": {
            k: (f"{t['cagr']:.1%}", f"{t['vol']:.1%}", round(t["sharpe"], 2), f"{t['dd']:.0%}",
                f"{t['turnover']:.1%}") for k, t in table.items()},
        "monthly diff vs equal weight, t": {k: round(v, 2) for k, v in tstat.items()},
        "momentum IC mean / t; top-bottom spread a year / t": (
            round(float(ic.mean()), 3), round(tt(ic), 2), f"{spread.mean() * 12:.1%}",
            round(tt(spread), 2)),
        "view q median / share positive": (f"{lg['q'].median():.1%}",
                                           round(float((lg['q'] > 0).mean()), 2)),
        "share of view adopted, median (10-90%)": (
            round(float(lg["adopted"].median()), 2),
            [round(float(v), 2) for v in lg["adopted"].quantile([0.1, 0.9])]),
        "last month: sample mean range / posterior range": (
            f"{last['sample'].min():.0%} to {last['sample'].max():.0%}",
            f"{last['post'].min():.0%} to {last['post'].max():.0%}"),
    }


ASSET_MIXES = Path("docs/data/asset_mixes.csv")  # results only (return, risk), for the site


def _fixed(weights: dict):
    def strategy(mu, cov, window):
        return np.array([weights.get(name, 0.0) for name in mu.index])
    return strategy


def report_assets(out_dir: Path) -> dict:
    """NIFTY, gold, government bonds and US equity for a rupee investor, Aug 2016 onwards."""
    from ef.assets import ASSETS_PATH, CLASSES, combine, fetch_yahoo, load_lake_indices
    from ef.costs import trade_cost
    from ef.walkforward import walk_forward

    if ASSETS_PATH.exists():
        yahoo = pd.read_parquet(ASSETS_PATH)
    else:
        yahoo = fetch_yahoo()
        ASSETS_PATH.parent.mkdir(exist_ok=True)
        yahoo.to_parquet(ASSETS_PATH)
    px = combine(yahoo, load_lake_indices())
    rf = float((px["cash"].iloc[-1] / px["cash"].iloc[0])
               ** (365.25 / (px.index[-1] - px.index[0]).days) - 1)
    weekly = px.resample("W-FRI").last().pct_change().dropna()
    yrs = (px.index[-1] - px.index[0]).days / 365.25
    cagr = lambda s: float((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1)  # noqa: E731
    assets = {c: {"cagr": cagr(px[c]), "vol": float(weekly[c].std() * np.sqrt(52)),
                  "dd": float((px[c] / px[c].cummax() - 1).min())}
              for c in [*CLASSES, "S&P 500 (USD)", "USDINR", "cash"]}
    corr = weekly[[*CLASSES, "USDINR"]].corr()

    mixes = {
        "NIFTY only": _fixed({"NIFTY 50": 1.0}),
        "60/40 NIFTY / bonds": _fixed({"NIFTY 50": 0.6, "government bonds": 0.4}),
        "60/20/20 NIFTY / bonds / gold": _fixed({"NIFTY 50": 0.6, "government bonds": 0.2,
                                                 "gold": 0.2}),
        "equal, all four": _equal,
        "risk parity, all four": lambda mu, cov, w: risk_parity(cov.to_numpy()),
        "min variance, all four": lambda mu, cov, w: min_variance(cov.to_numpy()),
        "max Sharpe, all four": lambda mu, cov, w: max_sharpe(mu.to_numpy(), cov.to_numpy(), rf),
    }
    out = walk_forward(px[CLASSES], lambda day: list(CLASSES), mixes, TRADING_DAYS,
                       cost=lambda b, s_, n, g: trade_cost(b, s_, n, CAPITAL * g))
    rets = out["returns"]
    # Weekly returns, like the asset table: a weekday calendar carries holidays as zero days.
    wk = (1 + rets).resample("W-FRI").prod() - 1
    cash = px["cash"].loc[rets.index[0]:]
    rf_mix = float((cash.iloc[-1] / cash.iloc[0])
                   ** (365.25 / (cash.index[-1] - cash.index[0]).days) - 1)
    dd = lambda r: float(((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min())  # noqa: E731
    table = {k: {**stats(wk[k], rf_mix), "dd": dd(rets[k])} for k in mixes}
    for k in table:
        table[k]["sharpe"] = (table[k]["cagr"] - rf_mix) / table[k]["vol"]
    avg_w = {k: pd.DataFrame(out["weights"][k]).T.mean() for k in
             ("risk parity, all four", "min variance, all four", "max Sharpe, all four")}
    pd.DataFrame(table).T.rename_axis("mix")[["cagr", "vol", "sharpe", "dd"]].to_csv(
        ASSET_MIXES, float_format="%.4f")

    colors = dict(zip([*CLASSES, "cash"], [plots.SERIES[0], plots.SERIES[3], plots.SERIES[2],
                                           plots.SERIES[1], plots.MUTED], strict=True))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for c in [*CLASSES, "cash"]:
        g = px[c] / px[c].iloc[0]
        ax.plot(g.index, g, color=colors[c], lw=1.2 if c == "cash" else 1.8,
                label=f"{c}: {assets[c]['cagr']:.1%} a year")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator([1, 1.5, 2, 3, 4, 5]))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"₹{v:g}"))
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_ylabel("growth of ₹1 (log scale)")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title(f"Four asset classes in rupees, {px.index[0]:%b %Y} to {px.index[-1]:%b %Y}")
    plots.save(fig, out_dir, "assets_growth")

    fig, ax = plt.subplots(figsize=(6.4, 5))
    labels = [*CLASSES, "USD/INR"]
    im = ax.imshow(corr.to_numpy(), cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
        "div", [plots.SERIES[1], plots.SURFACE, plots.SERIES[0]]), vmin=-1, vmax=1)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=9)
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(labels)), labels, fontsize=9)
    ax.grid(False)
    fig.colorbar(im, ax=ax, shrink=0.8, label="correlation of weekly returns")
    ax.set_title("Gold and bonds barely moved with NIFTY; the dollar rose when NIFTY fell")
    plots.save(fig, out_dir, "assets_correlation")

    fig, ax = plt.subplots(figsize=(9, 5))
    mix_colors = [plots.TEXT, plots.SERIES[2], plots.SERIES[3], plots.SERIES[4],
                  plots.SERIES[6], plots.SERIES[0], plots.SERIES[1]]
    for (k, t), color in zip(table.items(), mix_colors, strict=True):
        ax.plot(t["vol"] * 100, t["cagr"] * 100, "o", ms=9, color=color,
                markeredgecolor=plots.SURFACE, label=f"{k} (worst fall {t['dd']:.0%})")
    ax.set_xlim(0, None)
    ax.set_xlabel("volatility, % a year")
    ax.set_ylabel("return after costs, % a year")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=8, frameon=False)
    ax.set_title("Adding gold and bonds to NIFTY cut risk more than return (Jul 2017 on)")
    plots.save(fig, out_dir, "assets_mixes")

    us_usd = px["S&P 500 (USD)"] / px["S&P 500 (USD)"].iloc[0]
    us_inr = px["US equity (INR)"] / px["US equity (INR)"].iloc[0]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot(us_usd.index, us_usd, color=plots.MUTED, label=f"in dollars: "
            f"{assets['S&P 500 (USD)']['cagr']:.1%} a year")
    ax.plot(us_inr.index, us_inr, color=plots.SERIES[1], label=f"in rupees: "
            f"{assets['US equity (INR)']['cagr']:.1%} a year")
    ax.set_ylabel("growth of 1 unit, S&P 500 with dividends")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title(f"The rupee's fall added {assets['USDINR']['cagr']:.1%} a year to US shares")
    plots.save(fig, out_dir, "assets_rupee")

    a, b = "2020-02-19", "2020-03-23"
    covid = (px.loc[b] / px.loc[a] - 1)[[*CLASSES, "S&P 500 (USD)", "USDINR"]]
    return {
        "window": f"{px.index[0]:%Y-%m-%d} to {px.index[-1]:%Y-%m-%d}; cash {rf:.1%} "
                  f"(over the mixes' period {rf_mix:.1%})",
        "assets (cagr, vol, worst fall)": {k: (f"{v['cagr']:.1%}", f"{v['vol']:.1%}",
                                               f"{v['dd']:.0%}") for k, v in assets.items()},
        "weekly correlations with NIFTY": corr["NIFTY 50"].round(2).to_dict(),
        "mixes after costs (cagr, vol, sharpe vs cash, worst fall)": {
            k: (f"{t['cagr']:.1%}", f"{t['vol']:.1%}", round(t["sharpe"], 2), f"{t['dd']:.0%}")
            for k, t in table.items()},
        "average weights": {k: {c: f"{v:.0%}" for c, v in w.items()} for k, w in avg_w.items()},
        "first rebalance": f"{min(out['weights']['NIFTY only']):%Y-%m-%d}",
        "covid fall 19 Feb - 23 Mar 2020": {k: f"{v:.1%}" for k, v in covid.items()},
    }


REPORTS = {"frontier": report_frontier, "estimation": report_estimation,
           "covariance": report_covariance, "contest": report_contest,
           "constraints": report_constraints, "black-litterman": report_black_litterman,
           "assets": report_assets}
