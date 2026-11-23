import numpy as np
import pytest

from ef.black_litterman import implied_returns, posterior
from ef.frontier import max_utility

VOL = np.array([0.15, 0.22, 0.30, 0.18])
CORR = np.array([[1, .3, .2, .4], [.3, 1, .5, .3], [.2, .5, 1, .2], [.4, .3, .2, 1]])
COV = np.outer(VOL, VOL) * CORR
W0 = np.full(4, 0.25)
P = np.array([[0.5, 0.5, -0.5, -0.5]])  # assets 1-2 beat assets 3-4 by q
Q = np.array([0.05])


def test_no_views_returns_the_prior():
    pi = implied_returns(COV, W0, delta=2.5)
    mu, _ = posterior(pi, COV, np.empty((0, 4)), np.empty(0), np.empty((0, 0)))
    np.testing.assert_allclose(mu, pi)


def test_confidence_moves_the_posterior_between_prior_and_view():
    pi = implied_returns(COV, W0, delta=2.5)
    weak, _ = posterior(pi, COV, P, Q, np.array([[1e6]]))
    strong, _ = posterior(pi, COV, P, Q, np.array([[1e-12]]))
    mid, _ = posterior(pi, COV, P, Q, np.array([[0.05 * (P @ COV @ P.T).item()]]))
    np.testing.assert_allclose(weak, pi, atol=1e-6)
    assert (P @ strong).item() == pytest.approx(Q.item(), abs=1e-6)
    assert (P @ pi).item() < (P @ mid).item() < Q.item()


def test_posterior_covariance_adds_estimation_uncertainty():
    pi = implied_returns(COV, W0, delta=2.5)
    _, cov_bl = posterior(pi, COV, P, Q, np.array([[0.01]]))
    assert np.all(np.linalg.eigvalsh(cov_bl - COV) > 0)


def test_reverse_optimisation_recovers_the_prior_weights():
    pi = implied_returns(COV, W0, delta=2.5)
    np.testing.assert_allclose(max_utility(pi, COV, delta=2.5), W0, atol=1e-5)


def _trending(n_days=756, n=30, seed=0, persist=True):
    rng = np.random.default_rng(seed)
    drift = rng.normal(0, 0.0008, n) if persist else np.zeros(n)
    import pandas as pd

    return pd.DataFrame(rng.normal(0, 0.01, (n_days, n)) + drift,
                        columns=[f"S{i}" for i in range(n)])


def test_momentum_view_is_long_top_short_bottom_and_sums_to_zero():
    from ef.black_litterman import momentum_view

    p, q, omega = momentum_view(_trending(), top=5)
    assert p.sum() == pytest.approx(0)
    assert (p > 0).sum() == 5 and (p < 0).sum() == 5 and p.max() == pytest.approx(0.2)
    assert omega > 0


def test_momentum_view_size_comes_from_the_window():
    from ef.black_litterman import momentum_view

    strong = np.mean([momentum_view(_trending(seed=s), top=5)[1] for s in range(5)])
    none = np.mean([momentum_view(_trending(seed=s, persist=False), top=5)[1]
                    for s in range(5)])
    assert strong > 0.05 and abs(none) < strong / 2
