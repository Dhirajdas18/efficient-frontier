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


def test_resampled_max_sharpe_averages_bootstrap_weights():
    from ef.frontier import resampled_max_sharpe

    rng = np.random.default_rng(4)
    daily = rng.multivariate_normal(MU / 252, COV / 252, 750)
    w = resampled_max_sharpe(daily, rf=0.065, n_boot=20, seed=1)
    assert w.sum() == pytest.approx(1) and (w >= -1e-9).all()
    assert (w > 0.01).sum() >= (max_sharpe(daily.mean(0) * 252, np.cov(daily.T) * 252,
                                           0.065) > 0.01).sum()  # spreads, never concentrates more


def test_max_sharpe_with_no_stock_above_the_risk_free_rate_is_min_variance():
    np.testing.assert_allclose(max_sharpe(MU - 0.5, COV, rf=0.065), min_variance(COV), atol=1e-5)


def test_max_sharpe_respects_a_cap():
    w = max_sharpe(MU, COV, rf=0.065, bounds=(0.0, 0.3))
    assert (w <= 0.3 + 1e-7).all() and w.sum() == pytest.approx(1)


def test_max_sharpe_survives_awkward_bootstrap_samples():
    rng = np.random.default_rng(11)
    n = 40
    vol = rng.uniform(0.15, 0.5, n)
    corr = 0.3 + 0.7 * np.eye(n)
    cov = np.outer(vol, vol) * corr
    for seed in range(30):
        mu = np.random.default_rng(seed).normal(0.05, 0.3, n)
        w = max_sharpe(mu, cov, rf=0.065)
        assert w.sum() == pytest.approx(1) and (w >= -1e-8).all()


def test_risk_parity_equalises_risk_contributions():
    from ef.frontier import risk_parity

    w = risk_parity(COV)
    contrib = w * (COV @ w)
    np.testing.assert_allclose(contrib / contrib.sum(), np.full(4, 0.25), atol=1e-6)
    assert w.sum() == pytest.approx(1) and (w > 0).all()


def test_risk_parity_without_correlation_is_inverse_volatility():
    from ef.frontier import risk_parity

    diag = np.diag(VOL**2)
    inv = (1 / VOL) / (1 / VOL).sum()
    np.testing.assert_allclose(risk_parity(diag), inv, atol=1e-6)


SECT = np.array(["bank", "bank", "it", "it"])


def test_min_variance_respects_stock_and_sector_caps():
    w = min_variance(COV, bounds=(0.0, 0.4), sectors=SECT, sector_cap=0.6)
    assert (w <= 0.4 + 1e-7).all()
    for s in ("bank", "it"):
        assert w[SECT == s].sum() <= 0.6 + 1e-7


def test_max_sharpe_respects_sector_caps():
    w = max_sharpe(MU, COV, rf=0.065, sectors=SECT, sector_cap=0.55)
    for s in ("bank", "it"):
        assert w[SECT == s].sum() <= 0.55 + 1e-6
    assert w.sum() == pytest.approx(1)


def test_turnover_penalty_moves_less_from_the_previous_weights():
    from ef.frontier import min_variance_penalised

    prev = np.array([0.7, 0.1, 0.1, 0.1])
    free = min_variance(COV)
    np.testing.assert_allclose(min_variance_penalised(COV, prev, 0.0), free, atol=1e-5)
    moves = [np.abs(min_variance_penalised(COV, prev, lam) - prev).sum()
             for lam in (0.0, 0.002, 0.01, 1.0)]
    assert all(b <= a + 1e-9 for a, b in zip(moves, moves[1:], strict=False))  # never more
    assert moves[0] > 0.1 and moves[-1] < 1e-6  # no penalty trades; a huge one doesn't
