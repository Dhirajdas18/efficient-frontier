import numpy as np
import pandas as pd
import pytest

from ef.reports import stats


def test_stats_annualise_by_calendar_time_not_a_fixed_day_count():
    days = pd.bdate_range("2020-01-01", "2023-12-31")
    days = days[::2]  # about 130 observations a year
    r = pd.Series(0.001, index=days)
    out = stats(r, rf=0.0)
    years = (days[-1] - days[0]).days / 365.25
    assert out["cagr"] == pytest.approx(1.001 ** ((len(days) - 1) / years) - 1, rel=1e-3)
    noisy = pd.Series(np.random.default_rng(0).normal(0, 0.01, len(days)), index=days)
    per_year = (len(days) - 1) / years
    assert stats(noisy)["vol"] == pytest.approx(noisy.std() * np.sqrt(per_year), rel=1e-6)
