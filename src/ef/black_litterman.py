"""Black-Litterman: start from the returns a neutral portfolio implies, then blend in views.

- implied_returns: reverse optimisation, pi = delta · Σ · w_ref: the expected returns under which
  a mean-variance investor with risk aversion delta would hold w_ref.
- posterior: views P·mu = q with uncertainty Omega, blended with the prior pi (uncertainty τΣ):
  M = [(τΣ)⁻¹ + Pᵀ Ω⁻¹ P]⁻¹,  mu = M [(τΣ)⁻¹ pi + Pᵀ Ω⁻¹ q],  Σ_BL = Σ + M  (He & Litterman 1999).
"""

import numpy as np


def implied_returns(cov, w_ref, delta: float = 2.5) -> np.ndarray:
    return delta * np.asarray(cov, dtype=float) @ np.asarray(w_ref, dtype=float)


def posterior(pi, cov, p, q, omega, tau: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    pi, cov = np.asarray(pi, dtype=float), np.asarray(cov, dtype=float)
    p, q, omega = (np.atleast_2d(np.asarray(p, dtype=float)), np.asarray(q, dtype=float),
                   np.atleast_2d(np.asarray(omega, dtype=float)))
    prior_prec = np.linalg.inv(tau * cov)
    if p.size == 0:
        return pi.copy(), cov + tau * cov
    view_prec = p.T @ np.linalg.inv(omega) @ p
    m = np.linalg.inv(prior_prec + view_prec)
    mu = m @ (prior_prec @ pi + p.T @ np.linalg.inv(omega) @ q)
    return mu, cov + m


def momentum_view(daily, top: int = 10, formation: int = 252, skip: int = 21,
                  hold: int = 21, periods: int = 252):
    """A relative view from 12-1 momentum, sized and weighted by the window's own history.

    `daily`: a DataFrame of daily returns (rows = days, oldest first), the estimation window only.
    The view portfolio P is long the `top` stocks with the highest return over the `formation`
    days ending `skip` days ago and short the `top` lowest (each ±1/top). q is the average
    realised spread of that portfolio over the next `hold` days, measured at every month-sized
    step inside the window and annualised; Omega is the variance of that average (fewer or
    noisier months ⇒ less confidence). Returns (P as a Series, q, Omega).
    """
    import pandas as pd

    x = np.log1p(daily.fillna(0.0))

    def portfolio(end: int) -> pd.Series:
        mom = x.iloc[end - formation:end - skip].sum()
        p = pd.Series(0.0, index=x.columns)
        p[mom.nlargest(top).index] = 1 / top
        p[mom.nsmallest(top).index] = -1 / top
        return p

    spreads = []
    for end in range(formation, len(x) - hold + 1, hold):
        fwd = x.iloc[end:end + hold].sum()
        spreads.append(float(portfolio(end) @ fwd))
    spreads = np.array(spreads)
    per_year = periods / hold
    q = float(spreads.mean() * per_year)
    omega = float(spreads.var(ddof=1) * per_year**2 / len(spreads))
    return portfolio(len(x)), q, omega
