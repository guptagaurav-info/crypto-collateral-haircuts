"""Haircut rules. Every rule sees prices up to and including the margin date t, never after it.

A haircut h means the lender advances (1 - h) per $1 of collateral marked at the day-t close.
The rule is breached if the collateral loses more than h between t and close-out at t + MPOR.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODELS = ["fixed", "hist1y", "fhs", "fhs_floor"]
LABELS = {
    "fixed": "Static grid (illustrative)",
    "hist1y": "1-year historical VaR (baseline)",
    "fhs": "Volatility-scaled (EWMA FHS)",
    "fhs_floor": "Volatility-scaled + 10-year floor",
}


def _h_from_logq(q: pd.Series, cap: float) -> pd.Series:
    """Convert a lower-tail log-return quantile into a haircut in [0, cap]."""
    return (1.0 - np.exp(q)).clip(lower=0.0, upper=cap)


def ewma_vol(r: pd.Series, lam: float, seed_days: int = 30) -> pd.Series:
    """RiskMetrics EWMA volatility; sigma[t] uses returns up to and including t."""
    x = r.to_numpy()
    out = np.full(len(x), np.nan)
    valid = np.where(~np.isnan(x))[0]
    if len(valid) <= seed_days:
        return pd.Series(out, index=r.index)
    start = valid[seed_days]
    var = np.nanmean(x[valid[0]:start] ** 2)
    for i in range(start, len(x)):
        if not np.isnan(x[i]):
            var = lam * var + (1 - lam) * x[i] ** 2
        out[i] = np.sqrt(var)
    return pd.Series(out, index=r.index)


def haircuts_for_asset(p: pd.Series, asset: str, cfg: dict, mpor: int) -> pd.DataFrame:
    """All rules for one asset. p: daily close, contiguous after first valid date."""
    hc = cfg["haircut"]
    a = 1 - hc["confidence"]
    cap = hc["max_haircut"]
    p = p.loc[p.first_valid_index(): p.last_valid_index()]
    lp = np.log(p)
    r = lp.diff()
    RH = lp - lp.shift(mpor)                      # backward H-day log return, known at t
    age = pd.Series(np.arange(len(p)), index=p.index)
    minh = hc["min_history_days"]

    out = pd.DataFrame(index=p.index)
    grid = hc["fixed_grid"]
    out["fixed"] = float(grid.get(asset, grid["default"]))

    q_hist = RH.rolling(hc["hist_window_days"], min_periods=minh - mpor).quantile(a)
    out["hist1y"] = _h_from_logq(q_hist, cap)

    sig = ewma_vol(r, hc["ewma_lambda"])
    z = RH / (sig.shift(mpor) * np.sqrt(mpor))     # standardised by vol known at window start
    qz = z.rolling(hc["fhs_window_days"], min_periods=minh - mpor - 30).quantile(a)
    out["fhs"] = _h_from_logq(qz * sig * np.sqrt(mpor), cap)

    q_floor = RH.rolling(hc["floor_window_days"], min_periods=minh - mpor).quantile(a)
    floor = _h_from_logq(q_floor, cap)
    out["floor"] = floor
    out["fhs_floor"] = np.maximum(out["fhs"], floor)

    out["sigma"] = sig
    out["lendable"] = (age >= minh) & out[["hist1y", "fhs", "fhs_floor"]].notna().all(axis=1)
    # forward loss over the margin period of risk (positive = collateral lost value)
    out["loss"] = 1.0 - p.shift(-mpor) / p
    out["price"] = p
    return out


def build_panel(px: pd.DataFrame, cfg: dict, mpor: int, assets: list[str]) -> pd.DataFrame:
    frames = []
    for a in assets:
        d = haircuts_for_asset(px[a], a, cfg, mpor)
        d["asset"] = a
        frames.append(d)
    panel = pd.concat(frames).rename_axis("date").reset_index()
    t0, t1 = pd.Timestamp(cfg["test"]["start"]), pd.Timestamp(cfg["test"]["end"])
    panel["in_test"] = (panel["date"] >= t0) & (panel["date"] <= t1) & panel["lendable"] & panel["loss"].notna()
    return panel
