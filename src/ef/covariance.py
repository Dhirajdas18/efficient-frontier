"""Covariance estimators for daily returns (rows = days, columns = stocks), annualised (× 252).

- sample_cov: the plain sample covariance.
- ledoit_wolf_cc: Ledoit and Wolf (2004, "Honey, I shrunk the sample covariance matrix"):
  a weighted average of the sample covariance and a constant-correlation target (every pair at the
  average correlation, each stock keeping its own variance), with the weight estimated from the
  data to minimise expected error.
- ewma_cov: exponentially weighted covariance (recent days count more), RiskMetrics style.
"""

import numpy as np

TRADING_DAYS = 252


def sample_cov(x) -> np.ndarray:
    return np.cov(np.asarray(x, dtype=float).T) * TRADING_DAYS


def ledoit_wolf_cc(x, return_shrinkage: bool = False):
    x = np.asarray(x, dtype=float)
    t, n = x.shape
    x = x - x.mean(axis=0)
    sample = x.T @ x / t
    var = np.diag(sample)
    sd = np.sqrt(var)
    r_bar = (np.sum(sample / np.outer(sd, sd)) - n) / (n * (n - 1))
    prior = r_bar * np.outer(sd, sd)
    np.fill_diagonal(prior, var)
    # pi: sum of asymptotic variances of the sample entries
    phi_mat = (x**2).T @ (x**2) / t - sample**2
    phi = phi_mat.sum()
    # rho: asymptotic covariances between the target's and the sample's entries
    theta = (x**3).T @ x / t - var[:, None] * sample  # theta_ij = acov(s_ii, s_ij)
    np.fill_diagonal(theta, 0.0)
    rho = np.trace(phi_mat) + r_bar * np.sum(np.outer(1 / sd, sd) * theta)
    gamma = np.linalg.norm(sample - prior, "fro") ** 2
    shrink = float(np.clip((phi - rho) / gamma / t, 0.0, 1.0))
    est = (shrink * prior + (1 - shrink) * sample) * TRADING_DAYS
    return (est, shrink) if return_shrinkage else est


def ewma_cov(x, halflife: float = 63) -> np.ndarray:
    """Weights halve every `halflife` days going back; mean removed with the same weights."""
    x = np.asarray(x, dtype=float)
    lam = 0.5 ** (1 / halflife)
    w = lam ** np.arange(len(x))[::-1]
    w /= w.sum()
    xc = x - w @ x
    return (xc * w[:, None]).T @ xc / (1 - np.sum(w**2)) * TRADING_DAYS
