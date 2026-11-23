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


SECTIONS = [
    ("The efficient frontier",
     "Every NIFTY 50 stock (grey) and the long-only efficient frontier built from them, using the "
     "last three years of daily returns. Hover a point on the frontier to see what it holds. This "
     "looks back with perfect hindsight and uses today's index members: the next sections test "
     "what holds up out of sample.",
     frontier_figure),
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
