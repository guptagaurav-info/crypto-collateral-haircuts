"""Validation: breach tests, shortfall, procyclicality, book economics."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .models import MODELS


def kupiec(n: int, x: int, p: float) -> tuple[float, float]:
    """Kupiec proportion-of-failures LR test. Returns (LR, p-value)."""
    if n == 0:
        return np.nan, np.nan
    phat = x / n
    def ll(q):
        q = min(max(q, 1e-12), 1 - 1e-12)
        return (n - x) * np.log(1 - q) + x * np.log(q)
    lr = -2 * (ll(p) - ll(phat))
    return float(lr), float(1 - stats.chi2.cdf(lr, 1))


def christoffersen(seqs: list[np.ndarray]) -> tuple[float, float]:
    """Independence LR test pooled over assets: does a breach make the next breach more likely?"""
    n00 = n01 = n10 = n11 = 0
    for s in seqs:
        s = s.astype(int)
        a, b = s[:-1], s[1:]
        n00 += int(((a == 0) & (b == 0)).sum()); n01 += int(((a == 0) & (b == 1)).sum())
        n10 += int(((a == 1) & (b == 0)).sum()); n11 += int(((a == 1) & (b == 1)).sum())
    def safe(x):
        return np.log(x) if x > 0 else 0.0
    p01 = n01 / max(n00 + n01, 1); p11 = n11 / max(n10 + n11, 1)
    p = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    l0 = (n00 + n10) * safe(1 - p) + (n01 + n11) * safe(p)
    l1 = n00 * safe(1 - p01) + n01 * safe(p01) + n10 * safe(1 - p11) + n11 * safe(p11)
    lr = -2 * (l0 - l1)
    return float(lr), float(1 - stats.chi2.cdf(lr, 1)), float(p11)


def non_overlapping(panel: pd.DataFrame, mpor: int) -> pd.DataFrame:
    t = panel[panel["in_test"]].copy()
    t0 = t["date"].min()
    k = ((t["date"] - t0).dt.days % mpor) == 0
    return t[k]


def model_metrics(panel: pd.DataFrame, mpor: int, conf: float, models=MODELS) -> pd.DataFrame:
    t = panel[panel["in_test"]]
    nov = non_overlapping(panel, mpor)
    rows = []
    for m in models:
        br = t["loss"] > t[m]
        sf = (t["loss"] - t[m]).clip(lower=0)
        b2 = nov["loss"] > nov[m]
        lr, pv = kupiec(len(nov), int(b2.sum()), 1 - conf)
        seqs = [g.sort_values("date").pipe(lambda d: (d["loss"] > d[m]).to_numpy()) for _, g in nov.groupby("asset")]
        ilr, ipv, p11 = christoffersen(seqs)
        dh = (panel.sort_values("date").groupby("asset")[m].diff(5))
        dh = dh[panel["in_test"]]
        rows.append({
            "model": m,
            "asset_days": int(len(t)),
            "avg_haircut": float(t[m].mean()),
            "avg_haircut_btc": float(t.loc[t.asset == "btc", m].mean()),
            "avg_haircut_eth": float(t.loc[t.asset == "eth", m].mean()),
            "avg_haircut_alts": float(t.loc[~t.asset.isin(["btc", "eth"]), m].mean()),
            "breach_rate": float(br.mean()),
            "breach_rate_btc_eth": float(br[t.asset.isin(["btc", "eth"])].mean()),
            "breach_rate_alts": float(br[~t.asset.isin(["btc", "eth"])].mean()),
            "nonoverlap_windows": int(len(nov)), "nonoverlap_breaches": int(b2.sum()),
            "kupiec_lr": lr, "kupiec_p": pv,
            "indep_lr": ilr, "indep_p": ipv, "p_breach_after_breach": p11,
            "mean_shortfall_bp": float(1e4 * sf.mean()),
            "shortfall_given_breach_pct": float(100 * sf[br].mean()) if br.any() else 0.0,
            "worst_shortfall_pct": float(100 * sf.max()),
            "dh5_p99_pp": float(100 * dh.quantile(0.99)),
            "dh5_max_pp": float(100 * dh.max()),
        })
    return pd.DataFrame(rows)


def book_series(panel: pd.DataFrame, cfg: dict, models=MODELS) -> pd.DataFrame:
    """Illustrative cross-margined collateral book: 50% BTC, 25% ETH, 25% equally across live alts."""
    t = panel[panel["in_test"]].copy()
    w = cfg["book"]["weights"]
    alts = t[~t.asset.isin(["btc", "eth"])]
    n_alts = alts.groupby("date")["asset"].transform("count")
    t["w"] = np.where(t.asset == "btc", w["btc"], np.where(t.asset == "eth", w["eth"], np.nan))
    t.loc[alts.index, "w"] = w["others"] / n_alts
    out = {}
    g = t.groupby("date")
    out["loss"] = g.apply(lambda d: float((d.w * d.loss).sum()))
    for m in models:
        out[m] = g.apply(lambda d, m=m: float((d.w * d[m]).sum()))
    b = pd.DataFrame(out)
    b["n_assets"] = g.size()
    return b


def book_economics(book: pd.DataFrame, cfg: dict, mpor: int, models=MODELS) -> pd.DataFrame:
    C = cfg["book"]["collateral_usd"]
    ec = cfg["economics"]
    k = ec["margin_call_horizon_days"]
    rows = []
    for m in models:
        sf = (book["loss"] - book[m]).clip(lower=0) * C
        lend = (1 - book[m]) * C
        dh = book[m].diff(k) * C
        rows.append({
            "model": m,
            "avg_book_haircut": float(book[m].mean()),
            "avg_loan_capacity_usd": float(lend.mean()),
            "spread_revenue_usd_yr": float(lend.mean() * ec["lending_spread"]),
            "breach_days_per_yr": float((book["loss"] > book[m]).mean() * 365),
            "expected_shortfall_if_default_usd": float(sf.mean()),
            "expected_loss_usd_yr": float(sf.mean() * ec["client_pd_annual"]),
            "worst_shortfall_usd": float(sf.max()),
            "worst_shortfall_date": str(sf.idxmax().date()),
            "peak_margin_call_usd": float(dh.max()),
            "peak_margin_call_date": str(dh.idxmax().date()),
            "margin_call_p99_usd": float(dh.quantile(0.99)),
        })
    return pd.DataFrame(rows)
