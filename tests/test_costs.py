import pytest

from ef.costs import RATES, trade_cost


def test_buy_and_sell_costs_follow_the_rate_table():
    capital = 1_000_000.0
    buy = trade_cost(buy=0.1, sell=0.0, n_sells=0, capital=capital)
    sell = trade_cost(buy=0.0, sell=0.1, n_sells=1, capital=capital)
    side = (RATES["stt"] + (RATES["exchange"] + RATES["sebi"]) * (1 + RATES["gst"])
            + RATES["slippage"])
    assert buy == pytest.approx(0.1 * (side + RATES["stamp_buy"]))
    assert sell == pytest.approx(0.1 * side + RATES["dp_per_sell"] / capital)


def test_no_trades_cost_nothing():
    assert trade_cost(0.0, 0.0, 0, 1_000_000.0) == 0.0
