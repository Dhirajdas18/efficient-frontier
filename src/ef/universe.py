"""Point-in-time universe from a local NSE bhavcopy lake (set EF_LAKE_DIR), including stocks that
were later delisted. Ported from moving-average-backtest (mab/07). The 50 most-traded stocks by
median turnover over the prior 126 days, among stocks with F&O contracts, stand in for the NIFTY 50
at each date.
"""

import os
from pathlib import Path

import pandas as pd


def load_lake(lake_dir: str | Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(price index, turnover) as wide date x symbol frames from panel.parquet.

    Older lakes zero every daily move above 35% as a possible corporate action. For those, moves
    that match a split or bonus in actions.parquet stay zeroed and the rest (real crashes and
    rallies, e.g. YES Bank in March 2020) get their raw return back. A lake built with NSE's
    official corporate-actions list (_ref/nse_ca/*.csv) already flags only real corporate actions,
    so its flags are used as they are. Prices are rebuilt from returns.
    """
    lake_dir = lake_dir or os.environ.get("EF_LAKE_DIR")
    if not lake_dir:
        raise FileNotFoundError("set EF_LAKE_DIR to a bhavcopy lake folder with panel.parquet")
    lake_dir = Path(lake_dir)
    p = pd.read_parquet(lake_dir / "panel.parquet",
                        columns=["date", "symbol", "close", "prev_close", "ret", "ca_day",
                                 "turnover"])
    actions = lake_dir / "actions.parquet"
    known = set()
    if actions.exists():
        a = pd.read_parquet(actions, columns=["date", "symbol"])
        known = set(zip(a["symbol"], pd.to_datetime(a["date"]), strict=True))
    flagged = p["ca_day"].fillna(False).astype(bool)
    if any((lake_dir / "_ref" / "nse_ca").glob("*.csv")):
        known = None  # the lake was built with NSE's official list: its flags are already right
    matched = (flagged if known is None else
               pd.Series([(s, d) in known for s, d in zip(p["symbol"], p["date"], strict=True)],
                         index=p.index))
    raw = p["close"] / p["prev_close"] - 1
    ret = p["ret"].where(~(flagged & ~matched), raw)
    p = p.assign(ret=ret)
    rets = p.pivot_table(index="date", columns="symbol", values="ret").sort_index()
    traded = p.pivot_table(index="date", columns="symbol", values="close").sort_index().notna()
    prices = (1 + rets.fillna(0)).cumprod().where(traded)
    turnover = p.pivot_table(index="date", columns="symbol", values="turnover").sort_index()
    return prices, turnover


def members_at(turnover: pd.DataFrame, day: pd.Timestamp, n: int, window: int = 126,
               eligible: pd.DataFrame | None = None) -> list[str]:
    """The `n` most-traded stocks by median daily turnover over the `window` days before `day`.

    `eligible` (date x symbol, bool) limits the choice to stocks eligible on the last trading day
    before `day`, e.g. stocks with F&O contracts: NSE's own large-and-liquid filter, which keeps
    speculative small caps with spiky turnover out of a NIFTY 50 stand-in.
    """
    past = turnover.loc[turnover.index < day].iloc[-window:]  # known before the day starts
    med = past.median().dropna()
    if eligible is not None:
        prior = eligible.loc[eligible.index < day]
        if prior.empty:
            return []
        ok = prior.iloc[-1]
        med = med[med.index.isin(ok[ok].index)]
    return list(med.nlargest(n).index)


def load_fno(lake_dir: str | Path | None = None) -> pd.DataFrame:
    """Date x symbol: True where the stock had futures open interest (F&O-listed) that day."""
    lake_dir = Path(lake_dir or os.environ.get("EF_LAKE_DIR", ""))
    p = pd.read_parquet(lake_dir / "panel.parquet", columns=["date", "symbol", "fut_oi"])
    return p.assign(fno=p["fut_oi"].notna()).pivot_table(index="date", columns="symbol",
                                                         values="fno", aggfunc="any",
                                                         fill_value=False)
