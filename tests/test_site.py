import numpy as np
import pandas as pd

from ef.data import INDEX, SYMBOLS
from ef.site import build_html


def test_build_html_has_the_frontier_and_loads_plotly_once():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2024-01-01", periods=300)
    r = pd.DataFrame(rng.normal(0.0005, 0.015, (300, 51)), index=idx, columns=SYMBOLS + [INDEX])
    html = build_html(r)
    assert "The efficient frontier" in html and "efficient-frontier" in html
    assert html.count('src="https://cdn.plot.ly') == 1
