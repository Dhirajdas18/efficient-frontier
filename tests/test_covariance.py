import numpy as np
import pytest

from ef.covariance import ewma_cov, ledoit_wolf_cc, sample_cov


def _true(n=30, rho=0.3, seed=0):
    vol = np.random.default_rng(seed).uniform(0.15, 0.45, n) / np.sqrt(252)
    corr = rho + (1 - rho) * np.eye(n)
    return np.outer(vol, vol) * corr


def _draw(cov, t, seed):
    return np.random.default_rng(seed).multivariate_normal(np.zeros(len(cov)), cov, t)


def test_sample_cov_is_annualised():
    x = _draw(_true(), 5000, 1)
    np.testing.assert_allclose(sample_cov(x), np.cov(x.T) * 252)


def _varied(n=30, seed=0):
    """One-factor model with different loadings: correlations vary from pair to pair."""
    rng = np.random.default_rng(seed)
    beta = rng.uniform(0.2, 1.5, n)
    cov = np.outer(beta, beta) * 0.0002 + np.diag(rng.uniform(1e-4, 6e-4, n))
    return cov


def test_shrinkage_is_between_zero_and_one_and_falls_with_more_data():
    cov = _varied()
    short = ledoit_wolf_cc(_draw(cov, 60, 2), return_shrinkage=True)[1]
    long = ledoit_wolf_cc(_draw(cov, 5000, 2), return_shrinkage=True)[1]
    assert 0 <= long < short <= 1


def test_shrinkage_beats_sample_cov_when_data_is_short():
    cov = _true() * 252
    err_s, err_lw = [], []
    for seed in range(20):
        x = _draw(cov / 252, 60, seed)
        err_s.append(np.linalg.norm(sample_cov(x) - cov))
        err_lw.append(np.linalg.norm(ledoit_wolf_cc(x) - cov))
    assert np.mean(err_lw) < 0.8 * np.mean(err_s)


def test_estimates_are_symmetric_positive_definite():
    x = _draw(_true(), 40, 3)  # fewer days than stocks would make the sample singular
    for est in (ledoit_wolf_cc(x), ewma_cov(x, halflife=20)):
        np.testing.assert_allclose(est, est.T)
        assert np.linalg.eigvalsh(est).min() > 0


def test_ewma_weights_recent_days_more():
    calm = np.random.default_rng(4).normal(0, 0.01, (500, 2))
    wild = np.random.default_rng(5).normal(0, 0.03, (20, 2))
    x = np.vstack([calm, wild])
    assert ewma_cov(x, halflife=10)[0, 0] > 3 * sample_cov(x)[0, 0]
    assert ewma_cov(x, halflife=10**6)[0, 0] == pytest.approx(sample_cov(x)[0, 0], rel=0.05)
