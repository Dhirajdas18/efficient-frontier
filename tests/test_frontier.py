import numpy as np
import pytest

from ef.frontier import frontier, max_sharpe, min_variance, port_stats

RNG = np.random.default_rng(0)
MU = np.array([0.10, 0.14, 0.18, 0.12])
VOL = np.array([0.15, 0.22, 0.30, 0.18])
CORR = np.array([[1, .3, .2, .4], [.3, 1, .5, .3], [.2, .5, 1, .2], [.4, .3, .2, 1]])
COV = np.outer(VOL, VOL) * CORR


def test_two_assets_match_the_closed_form():
    cov = COV[:2, :2]
    w = np.array([0.4, 0.6])
    ret, vol = port_stats(w, MU[:2], cov)
    assert ret == pytest.approx(0.4 * 0.10 + 0.6 * 0.14)
    assert vol == pytest.approx(np.sqrt(0.16 * .15**2 + .36 * .22**2 + 2 * .24 * .3 * .15 * .22))


def test_unconstrained_min_variance_is_the_closed_form():
    ones = np.ones(4)
    exact = np.linalg.solve(COV, ones)
    exact /= exact.sum()
    np.testing.assert_allclose(min_variance(COV, bounds=(-5, 5)), exact, atol=1e-5)


def test_long_only_weights_are_valid_and_beat_every_single_stock():
    w = min_variance(COV)
    assert w.sum() == pytest.approx(1) and (w >= -1e-9).all()
    assert port_stats(w, MU, COV)[1] <= VOL.min() + 1e-9


def test_max_sharpe_beats_random_portfolios():
    w = max_sharpe(MU, COV, rf=0.065)
    best = (port_stats(w, MU, COV)[0] - 0.065) / port_stats(w, MU, COV)[1]
    for _ in range(2000):
        x = RNG.dirichlet(np.ones(4))
        r, v = port_stats(x, MU, COV)
        assert (r - 0.065) / v <= best + 1e-6


def test_frontier_is_the_lowest_risk_for_each_return():
    pts = frontier(MU, COV, n=15)
    rets = [p["ret"] for p in pts]
    assert rets == sorted(rets)
    vols = [p["vol"] for p in pts]
    assert vols[0] == pytest.approx(port_stats(min_variance(COV), MU, COV)[1], abs=1e-6)
    for p in pts:  # no random long-only portfolio with at least that return has less risk
        x = RNG.dirichlet(np.ones(4), 3000)
        r = x @ MU
        v = np.sqrt(np.einsum("ij,jk,ik->i", x, COV, x))
        assert (v[r >= p["ret"] + 1e-9] >= p["vol"] - 1e-6).all()


def test_capped_frontier_respects_the_cap_and_tops_out_correctly():
    pts = frontier(MU, COV, n=8, bounds=(0.0, 0.4))
    assert all((p["weights"] <= 0.4 + 1e-7).all() for p in pts)
    assert pts[-1]["ret"] == pytest.approx(0.4 * 0.18 + 0.4 * 0.14 + 0.2 * 0.12, abs=1e-6)
