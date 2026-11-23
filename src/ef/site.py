"""Interactive dashboard: the NIFTY 50 efficient frontier and later topics, as one static page."""

import json
import re
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ef import plots

FONT = "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"

ICON = (
    "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22%3E"
    "%3Cpath d=%22M1 12 5 7l3 3 7-8%22 fill=%22none%22 stroke=%22%232a78d6%22"
    " stroke-width=%222%22/%3E"
    "%3C/svg%3E"
)

def _layout(fig: go.Figure, ytitle: str) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=plots.SURFACE,
        plot_bgcolor=plots.SURFACE,
        font=dict(family=FONT, color=plots.TEXT_2, size=13),
        hovermode="x unified",
        margin=dict(l=56, r=24, t=96, b=40),
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, xanchor="left"),
        yaxis=dict(title=ytitle, gridcolor=plots.GRID, zeroline=False, automargin=True),
        xaxis=dict(
            gridcolor=plots.GRID,
            rangeslider=dict(visible=False),
            rangeselector=dict(
                buttons=[dict(count=n, label=f"{n}y", step="year", stepmode="backward")
                         for n in (1, 3, 5)] + [dict(step="all", label="All")],
                x=1, xanchor="right", y=1.08, yanchor="bottom", bgcolor="white",
            ),
        ),
    )
    end = max(pd.Timestamp(max(t.x)) for t in fig.data)
    fig.update_xaxes(range=[end - pd.DateOffset(years=3), end])  # open on the last 3 years
    return fig


def _scatter_layout(fig: go.Figure, xtitle: str, ytitle: str) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=plots.SURFACE, plot_bgcolor=plots.SURFACE,
        font=dict(family=FONT, color=plots.TEXT_2, size=13), hovermode="closest",
        margin=dict(l=56, r=24, t=56, b=48),
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, xanchor="left"),
        xaxis=dict(title=xtitle, gridcolor=plots.GRID, zeroline=False, rangemode="tozero"),
        yaxis=dict(title=ytitle, gridcolor=plots.GRID, zeroline=False, automargin=True),
    )
    return fig


def _top(weights, names, k: int = 5) -> str:
    s = pd.Series(weights, index=names).nlargest(k)
    return "<br>".join(f"{n} {w:.0%}" for n, w in s.items() if w >= 0.005)


def frontier_figure(r: pd.DataFrame) -> go.Figure:
    """Today's NIFTY 50 frontier over the last three years; hover a point to see its holdings."""
    from ef.data import SYMBOLS
    from ef.frontier import frontier, max_sharpe, min_variance, port_stats
    from ef.reports import RF, estimates

    mu, cov = estimates(r[SYMBOLS])
    m, c = mu.to_numpy(), cov.to_numpy()
    pts = frontier(m, c, n=40)
    fig = go.Figure()
    fig.add_scatter(x=(np.sqrt(np.diag(c)) * 100).round(1).tolist(), y=(m * 100).round(1).tolist(),
                    mode="markers", name="single stocks", text=SYMBOLS,
                    marker=dict(size=7, color=plots.MUTED),
                    hovertemplate="%{text}: %{y:.1f}% return, %{x:.1f}% vol<extra></extra>")
    fig.add_scatter(x=[round(p["vol"] * 100, 2) for p in pts],
                    y=[round(p["ret"] * 100, 2) for p in pts], mode="lines+markers",
                    name="efficient frontier", line=dict(color=plots.SERIES[0], width=2),
                    marker=dict(size=5), text=[_top(p["weights"], SYMBOLS) for p in pts],
                    hovertemplate="%{y:.1f}% return, %{x:.1f}% vol<br>%{text}<extra></extra>")
    for w, name, color in ((min_variance(c), "minimum variance", plots.SERIES[2]),
                           (max_sharpe(m, c, RF), "maximum Sharpe", plots.SERIES[1]),
                           (np.full(len(m), 1 / len(m)), "equal weight", plots.SERIES[3])):
        ret, vol = port_stats(w, m, c)
        fig.add_scatter(x=[round(vol * 100, 2)], y=[round(ret * 100, 2)], mode="markers",
                        name=name, marker=dict(size=12, color=color),
                        text=[_top(w, SYMBOLS)],
                        hovertemplate=f"{name}: %{{y:.1f}}%, %{{x:.1f}}% vol<br>%{{text}}"
                                      "<extra></extra>")
    return _scatter_layout(fig, "volatility, % a year", "return, % a year")


def _growth_figure(path, colors) -> go.Figure:
    m = pd.read_csv(path, index_col="date", parse_dates=["date"])
    fig = go.Figure()
    x = list(m.index.strftime("%Y-%m-%d"))
    for col, color in zip(m.columns, colors, strict=True):
        fig.add_scatter(x=x, y=(1 + m[col]).cumprod().round(3).tolist(), name=col, mode="lines",
                        line=dict(color=color, width=2 if col != "NIFTY" else 1.4),
                        hovertemplate=f"{col}: ₹%{{y:.2f}}<extra></extra>")
    fig = _layout(fig, "growth of ₹1")
    fig.update_yaxes(type="log", autorange=True)
    fig.update_xaxes(range=None, autorange=True)
    return fig


def estimation_figure(_r) -> go.Figure:
    """Growth of ₹1 out of sample before costs (docs/data/estimation_monthly.csv)."""
    from ef.reports import ESTIMATION

    return _growth_figure(ESTIMATION, [plots.SERIES[3], plots.SERIES[2], plots.SERIES[1],
                                       plots.SERIES[6], plots.TEXT])


def contest_figure(_r) -> go.Figure:
    """Growth of ₹1 after Indian delivery costs (docs/data/contest_monthly.csv)."""
    from ef.reports import CONTEST

    return _growth_figure(CONTEST, [plots.SERIES[3], plots.SERIES[0], plots.SERIES[4],
                                    plots.SERIES[6], plots.SERIES[2], plots.SERIES[1],
                                    plots.TEXT])


def constraints_figure(_r) -> go.Figure:
    """Growth of ₹1 after costs, capped vs uncapped (docs/data/constraints_monthly.csv)."""
    from ef.reports import CONSTRAINTS

    return _growth_figure(CONSTRAINTS, [plots.MUTED, plots.SERIES[1], plots.SERIES[2],
                                        plots.SERIES[0]])


def black_litterman_figure(_r) -> go.Figure:
    """Growth of ₹1 after costs: prior, Black-Litterman, pure momentum (docs/data)."""
    from ef.reports import BL_MONTHLY

    return _growth_figure(BL_MONTHLY, [plots.SERIES[3], plots.SERIES[1], plots.SERIES[6],
                                       plots.MUTED, plots.TEXT])


def assets_figure(_r) -> go.Figure:
    """Return against risk of simple asset-class mixes (docs/data/asset_mixes.csv)."""
    from ef.reports import ASSET_MIXES

    m = pd.read_csv(ASSET_MIXES, index_col="mix")
    fig = go.Figure()
    fig.add_scatter(x=(m["vol"] * 100).round(1).tolist(), y=(m["cagr"] * 100).round(1).tolist(),
                    mode="markers+text", text=list(m.index), textposition="top center",
                    customdata=(m["dd"] * 100).round(0).tolist(),
                    marker=dict(size=12, color=plots.SERIES[0]), name="mixes",
                    hovertemplate="%{text}: %{y:.1f}% a year, %{x:.1f}% volatility, worst fall "
                                  "%{customdata:.0f}%<extra></extra>")
    return _scatter_layout(fig, "volatility, % a year", "return after costs, % a year")


def shrinkage_figure(_r) -> go.Figure:
    """Ledoit-Wolf shrinkage intensity at each monthly rebalance (docs/data)."""
    from ef.reports import SHRINKAGE

    d = pd.read_csv(SHRINKAGE, index_col="date", parse_dates=["date"])
    fig = go.Figure()
    for col, color in zip(d.columns, (plots.SERIES[0], plots.SERIES[1]), strict=False):
        v = d[col].dropna()
        fig.add_scatter(x=list(v.index.strftime("%Y-%m-%d")), y=(v * 100).round(1).tolist(),
                        name=f"estimated from {col}", mode="lines",
                        line=dict(color=color, width=2),
                        hovertemplate=f"{col}: %{{y:.0f}}% shrinkage<extra></extra>")
    fig = _layout(fig, "shrinkage toward constant correlation, %")
    fig.update_xaxes(range=None, autorange=True)
    return fig


SECTIONS = [
    ("The efficient frontier",
     "Every NIFTY 50 stock (grey) and the long-only efficient frontier built from them, using the "
     "last three years of daily returns. Hover a point on the frontier to see what it holds. This "
     "looks back with perfect hindsight and uses today's index members: the next sections test "
     "what holds up out of sample.",
     frontier_figure),
    ("Out of sample",
     "Each month since February 2016, every portfolio is rebuilt from the previous three years "
     "only, using the 50 most-traded stocks with F&O contracts at the time (no hindsight about "
     "index membership), then held for the month. Maximum Sharpe promised a Sharpe ratio of 2.2 "
     "and delivered 0.35; all of them ended near NIFTY.",
     estimation_figure),
    ("Covariance estimation",
     "How far Ledoit-Wolf shrinkage pulled each month's sample covariance toward a "
     "constant-correlation target. It shrinks more with one year of data than with three. For "
     "long-only minimum variance it barely changed the realised risk; with "
     "short positions allowed it cut it.",
     shrinkage_figure),
    ("After costs",
     "Six ways of weighting the same 50 stocks each month, after STT, stamp duty, exchange and "
     "depository charges and slippage on a ₹10 lakh portfolio. Returns ended within two points of "
     "each other and of NIFTY; risk did not: minimum variance was less volatile than inverse "
     "volatility in every year.",
     contest_figure),
    ("Constraints",
     "The reference model's caps (15% per stock, 30% per sector) and a penalty on trading. Capping cut "
     "maximum Sharpe's volatility from 24% to 20%; minimum variance barely needed the caps. A "
     "turnover penalty cut minimum variance's trading by three quarters at the same risk, saving "
     "0.37% a year in costs.",
     constraints_figure),
    ("Black-Litterman",
     "Black-Litterman starts from the returns that justify holding the equal-weight portfolio and "
     "blends in a view, here 12-1 momentum, sized and weighted by its own three-year track record. "
     "It kept about 6% of each month's view and ended within noise of equal weight; buying the "
     "momentum stocks outright returned 7.2% a year after costs, the lowest here, with 31% "
     "turnover a month.",
     black_litterman_figure),
    ("Asset classes",
     "NIFTY, gold, government bonds and US shares in rupees, mixed in simple fixed proportions or "
     "by an optimiser and rebalanced monthly after costs, July 2017 to November 2026. Gold and "
     "bonds barely moved with NIFTY, so mixing them in cut volatility and the worst fall far more "
     "than it cut return. Hover a point for its worst fall.",
     assets_figure),
]


REPO = "https://github.com/Dhirajdas18/efficient-frontier"
PAGE = Template((Path(__file__).with_name("page.html")).read_text(encoding="utf-8"))


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def build_html(data: pd.DataFrame) -> str:
    parts, nav, loaded = [], [], False
    for title, blurb, make in SECTIONS:
        out = make(data)
        if isinstance(out, str):
            body = out
        else:
            body = out.to_html(full_html=False, include_plotlyjs=False if loaded else "cdn",
                               config={"displaylogo": False, "responsive": True})
            loaded = True
        sid = _slug(title)
        nav.append(f'<li><a href="#{sid}">{title}</a></li>')
        parts.append(f'<section id="{sid}">\n<h2>{title}</h2>\n<p>{blurb}</p>\n{body}\n</section>')
    if not loaded:  # the page script expects Plotly
        parts.append('<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>')
    return PAGE.substitute(
        icon=ICON, font=FONT, repo=REPO, updated=f"{data.index[-1]:%d %b %Y}",
        surface=plots.SURFACE, text=plots.TEXT, text2=plots.TEXT_2, grid=plots.GRID,
        accent=plots.SERIES[0], d_surface=plots.DARK[plots.SURFACE], d_text=plots.DARK[plots.TEXT],
        d_text2=plots.DARK[plots.TEXT_2], d_grid=plots.DARK[plots.GRID],
        d_accent=plots.DARK[plots.SERIES[0]],
        dark=json.dumps({k.lower(): v for k, v in plots.DARK.items()}),
        dark_lines=json.dumps({k.lower(): v for k, v in plots.DARK_LINES.items()}),
        nav="\n".join(nav), sections="\n".join(parts),
    )
