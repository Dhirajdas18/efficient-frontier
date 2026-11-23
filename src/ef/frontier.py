"""Mean-variance portfolio maths: portfolio return and risk, minimum variance, maximum Sharpe and
the efficient frontier, long-only by default (weights between 0 and 1, summing to 1).

Inputs are annualised: `mu` expected returns, `cov` the covariance matrix.
"""

import numpy as np
from scipy.optimize import minimize


def port_stats(w, mu, cov) -> tuple[float, float]:
    """(expected return, volatility) of weights `w`."""
    w = np.asarray(w, dtype=float)
    return float(w @ mu), float(np.sqrt(w @ cov @ w))


def _solve(objective, n: int, bounds, extra=(), x0=None) -> np.ndarray:
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}, *extra]
    res = minimize(objective, np.full(n, 1 / n) if x0 is None else x0, method="SLSQP",
                   bounds=[bounds] * n, constraints=cons,
                   options={"ftol": 1e-12, "maxiter": 1000})
    if not res.success:
        raise RuntimeError(f"optimiser failed: {res.message}")
    return res.x


def _sector_constraints(sectors, cap, total=None):
    """Inequality constraints: each sector's weight <= cap (of `total(w)` if given)."""
    if sectors is None or cap is None:
        return []
    sectors = np.asarray(sectors)
    cons = []
    for s in np.unique(sectors):
        mask = (sectors == s).astype(float)
        if total is None:
            cons.append({"type": "ineq", "fun": lambda w, m=mask: cap - m @ w})
        else:
            cons.append({"type": "ineq", "fun": lambda w, m=mask: cap * total(w) - m @ w})
    return cons


def min_variance(cov, bounds=(0.0, 1.0), sectors=None, sector_cap=None) -> np.ndarray:
    """Lowest-volatility portfolio; optional per-stock bounds and per-sector cap."""
    cov = np.asarray(cov, dtype=float)
    return _solve(lambda w: w @ cov @ w, len(cov), bounds,
                  _sector_constraints(sectors, sector_cap))


def min_variance_penalised(cov, prev, penalty: float, bounds=(0.0, 1.0), sectors=None,
                           sector_cap=None) -> np.ndarray:
    """Minimum variance plus `penalty` × turnover from the previous (drifted) weights `prev`:
    minimise w'Σw + penalty · Σ|w - prev|. Turnover is split into buys u and sells v (w = prev +
    u - v, u, v >= 0) so the problem stays smooth; penalty is in annual-variance units per unit
    traded."""
    cov, prev = np.asarray(cov, dtype=float), np.asarray(prev, dtype=float)
    n = len(cov)
    if penalty == 0:
        return min_variance(cov, bounds, sectors, sector_cap)
    lo, hi = bounds
    weights = lambda z: prev + z[:n] - z[n:]  # noqa: E731
    cons = [{"type": "eq", "fun": lambda z: weights(z).sum() - 1},
            {"type": "ineq", "fun": lambda z: weights(z) - lo},
            {"type": "ineq", "fun": lambda z: hi - weights(z)}]
    if sectors is not None and sector_cap is not None:
        cons += [{"type": "ineq", "fun": lambda z, c=c: c["fun"](weights(z))}
                 for c in _sector_constraints(sectors, sector_cap)]
    target = min_variance(cov, bounds, sectors, sector_cap)
    z0 = np.concatenate([np.clip(target - prev, 0, None), np.clip(prev - target, 0, None)])
    res = minimize(lambda z: weights(z) @ cov @ weights(z) + penalty * z.sum(), z0,
                   method="SLSQP", bounds=[(0.0, None)] * (2 * n), constraints=cons,
                   options={"ftol": 1e-14, "maxiter": 2000})
    w = np.clip(weights(res.x), 0.0, None)
    return w / w.sum()


def max_sharpe(mu, cov, rf: float = 0.0, bounds=(0.0, 1.0), sectors=None,
               sector_cap=None) -> np.ndarray:
    """The tangency portfolio: highest (return - rf) / volatility, long-only.

    Solved as the convex problem: minimise y'Σy subject to (mu - rf)'y = 1, y >= 0, then
    w = y / sum(y); a cap c becomes y_i <= c * sum(y). If no stock beats rf there is no positive
    Sharpe to maximise, and the minimum-variance portfolio is returned.
    """
    mu, cov = np.asarray(mu, dtype=float), np.asarray(cov, dtype=float)
    excess = mu - rf
    if bounds[0] < 0:
        raise ValueError("max_sharpe is long-only")
    if (excess <= 0).all():
        return min_variance(cov, bounds, sectors, sector_cap)
    n, cap = len(mu), bounds[1]
    scale = float(np.mean(np.diag(cov)))  # keep the objective near 1 for the solver
    cons = [{"type": "eq", "fun": lambda y: excess @ y - 1}]
    if cap < 1:
        cons.append({"type": "ineq", "fun": lambda y: cap * y.sum() - y})
    cons += _sector_constraints(sectors, sector_cap, total=lambda y: y.sum())
    y0 = np.where(excess > 0, excess, 0.0)
    y0 /= excess @ y0
    res = minimize(lambda y: y @ cov @ y / scale, y0, method="SLSQP", bounds=[(0.0, None)] * n,
                   constraints=cons, options={"ftol": 1e-14, "maxiter": 2000})
    y = np.clip(res.x, 0.0, None)
    if not np.isfinite(y).all() or y.sum() <= 0 or abs(excess @ y - 1) > 1e-4:
        raise RuntimeError(f"optimiser failed: {res.message}")
    return y / y.sum()


def frontier(mu, cov, n: int = 50, bounds=(0.0, 1.0)) -> list[dict]:
    """`n` efficient portfolios from minimum variance up to the highest attainable return:
    each the lowest-risk portfolio for its target return. Dicts of ret, vol, weights."""
    mu, cov = np.asarray(mu, dtype=float), np.asarray(cov, dtype=float)
    w0 = min_variance(cov, bounds)
    lo = float(w0 @ mu)
    hi = float(_solve(lambda w: -(w @ mu), len(mu), bounds) @ mu)  # highest attainable return
    out, x = [], w0
    for target in np.linspace(lo, hi, n):
        x = _solve(lambda w: w @ cov @ w, len(mu), bounds,
                   [{"type": "ineq", "fun": lambda w, t=target: w @ mu - t}], x0=x)
        r, v = port_stats(x, mu, cov)
        out.append({"ret": r, "vol": v, "weights": x})
    return out


def resampled_max_sharpe(daily, rf: float = 0.0, n_boot: int = 50, seed=None,
                         bounds=(0.0, 1.0), periods: int = 252) -> np.ndarray:
    """Michaud-style resampling: re-estimate means and covariance on bootstrap resamples of the
    daily return rows, solve max Sharpe on each, and average the weights."""
    daily = np.asarray(daily, dtype=float)
    rng = np.random.default_rng(seed)
    out = np.zeros(daily.shape[1])
    for _ in range(n_boot):
        sample = daily[rng.integers(0, len(daily), len(daily))]
        out += max_sharpe(sample.mean(0) * periods, np.cov(sample.T) * periods, rf, bounds)
    return out / n_boot


def risk_parity(cov) -> np.ndarray:
    """Equal risk contribution, long-only: each stock adds the same share of portfolio variance.

    Solved in Spinu's (2013) convex form: minimise y'Σy / 2 - mean(log y) over y > 0, then
    w = y / sum(y). With no correlation this is inverse volatility.
    """
    cov = np.asarray(cov, dtype=float)
    n = len(cov)
    scale = float(np.mean(np.diag(cov)))
    c = cov / scale
    y0 = 1 / np.sqrt(np.diag(c))
    res = minimize(lambda y: 0.5 * y @ c @ y - np.log(y).sum() / n, y0,
                   jac=lambda y: c @ y - 1 / (n * y), method="L-BFGS-B",
                   bounds=[(1e-10, None)] * n, options={"ftol": 1e-15, "gtol": 1e-12,
                                                        "maxiter": 5000})
    y = res.x
    return y / y.sum()


def max_utility(mu, cov, delta: float = 2.5, bounds=(0.0, 1.0), sectors=None,
                sector_cap=None) -> np.ndarray:
    """Mean-variance optimum: maximise w'mu - delta/2 · w'Σw, fully invested."""
    mu, cov = np.asarray(mu, dtype=float), np.asarray(cov, dtype=float)
    scale = float(np.mean(np.diag(cov)))
    return _solve(lambda w: -(w @ mu - delta / 2 * w @ cov @ w) / scale, len(mu), bounds,
                  _sector_constraints(sectors, sector_cap))
