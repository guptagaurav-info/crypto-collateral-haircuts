"""Figures. Plain-English titles, units on axes, integer year ticks."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator, FuncFormatter

from .models import MODELS, LABELS

COL = {"fixed": "#8c8c8c", "hist1y": "#1f5fbf", "fhs": "#d98c1f", "fhs_floor": "#2e8b57"}
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 110, "savefig.dpi": 160, "axes.titleweight": "bold"})


def _years(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator(1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def _pct(ax, axis="y", nd=0):
    f = FuncFormatter(lambda v, _: f"{v:.{nd}f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def frontier(econ: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    for _, r in econ.iterrows():
        m = r["model"]
        ax.scatter(r["avg_loan_capacity_usd"] / 1e6, r["worst_shortfall_usd"] / 1e6, s=170, color=COL[m], zorder=3,
                   label=LABELS[m])
        ax.annotate(f"  {LABELS[m]}\n  lends \\${r['avg_loan_capacity_usd']/1e6:,.0f}M, worst loss \\${r['worst_shortfall_usd']/1e6:,.0f}M",
                    (r["avg_loan_capacity_usd"] / 1e6, r["worst_shortfall_usd"] / 1e6), fontsize=8.5, va="center")
    ax.set_xlabel("Average amount lent against \\$1bn of crypto collateral (\\$M)")
    ax.set_ylabel("Worst uncovered loss if the client defaults (\\$M)")
    ax.set_title("More lending buys more crash loss: the haircut trade-off, 2018-2026")
    ax.set_xlim(700, 960)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def btc_history(panel: pd.DataFrame, path, asset="btc", title="Bitcoin: haircut set each day vs the 2-day loss that followed"):
    d = panel[(panel.asset == asset) & panel.in_test].set_index("date")
    fig, ax = plt.subplots(figsize=(10, 5.2))
    loss = 100 * d["loss"].clip(lower=0)
    ax.scatter(d.index, loss, s=3, color="#bbbbbb", label="Realised 2-day loss (%)", zorder=1)
    for m in MODELS:
        ax.plot(d.index, 100 * d[m], lw=1.6 if m != "fixed" else 1.2, color=COL[m], label=LABELS[m], zorder=2)
    br = d[d["loss"] > d["hist1y"]]
    ax.scatter(br.index, 100 * br["loss"], s=22, facecolors="none", edgecolors="#b03a2e", lw=1.2,
               label="Loss above the 1-year VaR haircut", zorder=3)
    _years(ax); _pct(ax)
    ax.set_ylabel("Haircut / 2-day loss (% of collateral value)")
    ax.set_title(title)
    ax.legend(fontsize=8.5, ncol=2, loc="upper right", frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def breach_by_year(panel: pd.DataFrame, path):
    t = panel[panel.in_test].copy()
    t["yr"] = t.date.dt.year
    fig, ax = plt.subplots(figsize=(9.5, 5))
    yrs = sorted(t.yr.unique())
    w = 0.2
    for i, m in enumerate(MODELS):
        r = t.groupby("yr").apply(lambda g, m=m: 100 * (g.loss > g[m]).mean())
        ax.bar(np.array(yrs) + (i - 1.5) * w, r.values, width=w, color=COL[m], label=LABELS[m])
    ax.axhline(1.0, color="#b03a2e", ls="--", lw=1.2, label="Design target: 1 breach in 100")
    ax.xaxis.set_major_locator(MultipleLocator(1))
    ax.set_xlabel("Year"); ax.set_ylabel("Share of 2-day windows where loss exceeded the haircut (%)")
    ax.set_title("How often each haircut was too small, by year (all coins)")
    _pct(ax, nd=1)
    ax.legend(fontsize=8.5, frameon=False)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def stress_bars(stress: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ev = stress["event"].tolist()
    x = np.arange(len(ev))
    w = 0.16
    ax.bar(x - 2 * w, 100 * stress["book_loss"], width=w, color="#333333", label="Actual 2-day loss on the book")
    for i, m in enumerate(MODELS):
        ax.bar(x + (i - 1) * w, 100 * stress[m], width=w, color=COL[m], label=f"Haircut: {LABELS[m]}")
    ax.set_xticks(x, [e.replace(" ", "\n", 2) for e in ev], fontsize=8.5)
    ax.set_ylabel("% of collateral value")
    ax.set_title("Crash days: the haircut held vs the loss that followed (illustrative \\$1bn book)")
    _pct(ax)
    ax.set_ylim(0, 40)
    ax.legend(fontsize=8, frameon=False, ncol=2, loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def margin_calls(book: pd.DataFrame, path, k=5, C=1e9):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for m in ["hist1y", "fhs", "fhs_floor"]:
        ax.plot(book.index, book[m].diff(k).clip(lower=0) * C / 1e6, color=COL[m], lw=1.1, label=LABELS[m])
    _years(ax)
    ax.set_ylabel("Extra collateral demanded in 5 days (\\$M)")
    ax.set_title("Margin calls the rule itself creates: 5-day haircut increases on a \\$1bn book")
    ax.legend(fontsize=9, frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def mpor_chart(sens: pd.DataFrame, path):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    for m in MODELS:
        s = sens[sens.model == m]
        axes[0].plot(s.mpor, 100 * s.avg_haircut, marker="o", color=COL[m], label=LABELS[m])
        axes[1].plot(s.mpor, 100 * s.breach_rate, marker="o", color=COL[m], label=LABELS[m])
    axes[1].axhline(1.0, color="#b03a2e", ls="--", lw=1)
    for a in axes:
        a.set_xlabel("Days to close out a defaulted client"); a.xaxis.set_major_locator(MultipleLocator(1)); a.grid(alpha=0.3)
    axes[0].set_ylabel("Average haircut (%)"); _pct(axes[0])
    axes[1].set_ylabel("Breach rate (%)"); _pct(axes[1], nd=2)
    axes[0].set_title("Haircut needed"); axes[1].set_title("How often it was too small")
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("The close-out assumption drives the answer", fontweight="bold")
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
