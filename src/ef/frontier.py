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


def min_variance(cov, bounds=(0.0, 1.0)) -> np.ndarray:
    cov = np.asarray(cov, dtype=float)
    return _solve(lambda w: w @ cov @ w, len(cov), bounds)


def max_sharpe(mu, cov, rf: float = 0.0, bounds=(0.0, 1.0)) -> np.ndarray:
    """The tangency portfolio: highest (return - rf) / volatility."""
    mu, cov = np.asarray(mu, dtype=float), np.asarray(cov, dtype=float)
    return _solve(lambda w: -(w @ mu - rf) / np.sqrt(w @ cov @ w), len(mu), bounds)


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
