import pandas as pd
import pytest

from ef.universe import members_at


def _wide(values, start="2014-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.DataFrame(values, index=idx)


def test_members_use_only_past_turnover():
    idx = pd.bdate_range("2014-01-01", periods=200)
    t = pd.DataFrame({"A": 10.0, "B": 5.0, "C": 1.0}, index=idx)
    day = idx[150]
    assert members_at(t, day, 2, window=50) == ["A", "B"]
    t2 = t.copy()
    t2.loc[idx[151]:, "C"] = 1e9  # C becomes huge only in the future
    assert members_at(t2, day, 2, window=50) == ["A", "B"]


def test_members_exclude_the_rebalance_days_own_turnover():
    idx = pd.bdate_range("2014-01-01", periods=60)
    t = pd.DataFrame({"A": 10.0, "B": 5.0}, index=idx)
    t.loc[idx[50], "B"] = 1e9  # spike on the rebalance day itself
    assert members_at(t, idx[50], 1, window=1) == ["A"]  # window 1: only the day before


def test_lake_repair_restores_real_moves_not_matched_to_a_corporate_action(tmp_path):
    from ef.universe import load_lake

    idx = pd.bdate_range("2020-03-02", periods=4)
    panel = pd.DataFrame({
        "date": list(idx) * 2,
        "symbol": ["YES"] * 4 + ["SPLIT"] * 4,
        "close": [100.0, 44.0, 44.0, 44.0, 100.0, 50.0, 50.0, 50.0],
        "prev_close": [100.0, 100.0, 44.0, 44.0, 100.0, 100.0, 50.0, 50.0],
        "ret": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # both big days zeroed by the lake
        "ca_day": [False, True, False, False, False, True, False, False],
        "turnover": 1.0,
    })
    panel.to_parquet(tmp_path / "panel.parquet")
    pd.DataFrame({"date": [idx[1]], "symbol": ["SPLIT"], "ratio": [2.0]}).to_parquet(
        tmp_path / "actions.parquet")
    prices, _ = load_lake(tmp_path)
    assert prices["YES"].iloc[-1] / prices["YES"].iloc[0] == pytest.approx(0.44)  # real crash kept
    assert prices["SPLIT"].iloc[-1] / prices["SPLIT"].iloc[0] == pytest.approx(1.0)  # split ignored


def test_a_lake_built_with_the_official_nse_list_is_trusted_as_is(tmp_path):
    from ef.universe import load_lake

    idx = pd.bdate_range("2026-04-28", periods=3)
    panel = pd.DataFrame({
        "date": idx, "symbol": "VEDL",
        "close": [770.0, 271.0, 271.0], "prev_close": [770.0, 770.0, 271.0],
        "ret": [0.0, 0.0, 0.0],  # demerger day zeroed by the lake
        "ca_day": [False, True, False], "turnover": 1.0,
    })
    panel.to_parquet(tmp_path / "panel.parquet")
    (tmp_path / "_ref" / "nse_ca").mkdir(parents=True)
    (tmp_path / "_ref" / "nse_ca" / "nse_ca.csv").write_text("SYMBOL,PURPOSE,EX-DATE\n")
    prices, _ = load_lake(tmp_path)
    assert prices["VEDL"].iloc[-1] == pytest.approx(prices["VEDL"].iloc[0])  # not a fake crash


def test_members_can_be_limited_to_stocks_with_fno_contracts_the_day_before():
    from ef.universe import members_at

    idx = pd.bdate_range("2024-01-01", periods=10)
    turnover = pd.DataFrame({"BIG": 100.0, "SMALLCAP": 500.0, "NEW": 300.0}, index=idx)
    fno = pd.DataFrame(False, index=idx, columns=turnover.columns)
    fno["BIG"] = True
    fno.loc[idx[-1], "NEW"] = True  # becomes eligible only on the rebalance day itself
    assert members_at(turnover, idx[-1], 2, eligible=fno) == ["BIG"]
    assert members_at(turnover, idx[-1], 2) == ["SMALLCAP", "NEW"]


def test_load_nifty_reads_the_lakes_index_files(tmp_path):
    from ef.universe import load_nifty

    (tmp_path / "index").mkdir()
    for d, close in (("2024-01-01", 100.0), ("2024-01-02", 101.0)):
        pd.DataFrame({"date": [pd.Timestamp(d)] * 2, "index": ["Nifty 50", "Nifty Bank"],
                      "open": 0.0, "high": 0.0, "low": 0.0, "close": [close, 5.0]}) \
            .to_parquet(tmp_path / "index" / f"{d}.parquet")
    s = load_nifty(tmp_path)
    assert list(s) == [100.0, 101.0] and s.index[0] == pd.Timestamp("2024-01-01")


def test_a_session_missing_from_the_lake_keeps_its_move(tmp_path):
    from ef.universe import load_lake

    # 1 Feb is a special session missing from the panel: 3 Feb's prev_close is 1 Feb's close
    panel = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-31", "2020-02-03"]), "symbol": ["A", "A"],
        "close": [100.0, 95.0], "prev_close": [99.0, 97.0], "ret": [0.0101, 95 / 97 - 1],
        "ca_day": [False, False], "turnover": [1.0, 1.0]})
    panel.to_parquet(tmp_path / "panel.parquet")
    (tmp_path / "_ref" / "nse_ca").mkdir(parents=True)
    (tmp_path / "_ref" / "nse_ca" / "x.csv").write_text("SYMBOL,PURPOSE,EX-DATE\n")
    px, _ = load_lake(tmp_path)
    assert px["A"].iloc[1] / px["A"].iloc[0] == pytest.approx(0.95)
