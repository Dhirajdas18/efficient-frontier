"""Indian equity-delivery trading costs (Zerodha), as fractions of the portfolio.

Rates match the reference model's cost model (zerodha.com/charges, checked 2026-11): STT 0.1% on buys and
sells, stamp duty 0.015% on buys, NSE transaction charge 0.00322%, SEBI ₹10 per crore, 18% GST on
the exchange and SEBI charges (delivery brokerage is zero), a ₹15.93 depository (DP) charge per
stock sold per day, and 0.05% slippage per side.
"""

RATES = {
    "stt": 0.001,
    "stamp_buy": 0.00015,
    "exchange": 0.0000322,
    "sebi": 0.000001,
    "gst": 0.18,
    "dp_per_sell": 15.93,  # ₹ per stock sold per day
    "slippage": 0.0005,
}


def trade_cost(buy: float, sell: float, n_sells: int, capital: float,
               rates: dict = RATES) -> float:
    """Cost of one rebalance as a fraction of the portfolio: `buy` and `sell` are traded values
    as fractions of the portfolio, `n_sells` the number of stocks sold, `capital` its ₹ value."""
    fees = (rates["exchange"] + rates["sebi"]) * (1 + rates["gst"])
    per_side = fees + rates["slippage"] + rates["stt"]
    return (buy * (per_side + rates["stamp_buy"]) + sell * per_side
            + n_sells * rates["dp_per_sell"] / capital)
