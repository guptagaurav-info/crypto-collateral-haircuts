"""End to end: data -> haircuts -> walk-forward validation -> reports/."""
from __future__ import annotations

import json
import random

import numpy as np
import pandas as pd

from . import backtest, config, ingest, models, report
from .config import ROOT


def run(cfg: dict | None = None) -> dict:
    cfg = cfg or config.load()
    random.seed(cfg["seed"]); np.random.seed(cfg["seed"])
    out = ROOT / cfg["out_dir"]; fig = out / "figures"; fig.mkdir(parents=True, exist_ok=True)

    manifest = ingest.download(cfg)
    px = ingest.load_prices(cfg)
    dq = ingest.data_quality(px); dq.to_csv(out / "data_quality.csv", index=False)

    H = cfg["haircut"]["mpor_days"]; conf = cfg["haircut"]["confidence"]
    panel = models.build_panel(px, cfg, H, cfg["assets"])
    mm = backtest.model_metrics(panel, H, conf)
    mm.to_csv(out / "model_metrics.csv", index=False)

    book = backtest.book_series(panel, cfg)
    econ = backtest.book_economics(book, cfg, H)
    econ.to_csv(out / "book_economics.csv", index=False)

    # split halves
    split = pd.Timestamp(cfg["test"]["split_date"])
    halves = {}
    for name, mask in {"first": panel.date < split, "second": panel.date >= split}.items():
        p = panel.copy(); p["in_test"] = p["in_test"] & mask
        halves[name] = backtest.model_metrics(p, H, conf).set_index("model")[
            ["avg_haircut", "breach_rate", "mean_shortfall_bp", "worst_shortfall_pct"]].to_dict("index")

    # stress events (book level, plus worst single coin)
    rows = []
    for ev, d in cfg["stress_events"].items():
        d = pd.Timestamp(d)
        b = book.loc[d]
        day = panel[(panel.date == d) & panel.in_test]
        worst = day.loc[day.loss.idxmax()]
        r = {"event": ev, "date": str(d.date()), "book_loss": float(b["loss"]),
             "worst_coin": worst.asset, "worst_coin_loss": float(worst.loss)}
        for m in models.MODELS:
            r[m] = float(b[m]); r[f"shortfall_{m}_usd"] = float(max(b["loss"] - b[m], 0) * cfg["book"]["collateral_usd"])
        rows.append(r)
    stress = pd.DataFrame(rows); stress.to_csv(out / "stress_events.csv", index=False)
    yrs = (book.index.max() - book.index.min()).days / 365.25
    econ["crash_loss_total_usd"] = [float(stress[f"shortfall_{m}_usd"].sum()) for m in econ["model"]]
    econ["crash_events_breached"] = [int((stress[f"shortfall_{m}_usd"] > 0).sum()) for m in econ["model"]]
    econ["test_years"] = yrs
    econ["revenue_over_test_usd"] = econ["spread_revenue_usd_yr"] * yrs
    econ.to_csv(out / "book_economics.csv", index=False)
    base = econ.set_index("model").loc["hist1y"]
    breakeven = {}
    for m in ["fixed", "fhs_floor"]:
        r = econ.set_index("model").loc[m]
        rev_given_up = base["revenue_over_test_usd"] - r["revenue_over_test_usd"]
        crash_saved = base["crash_loss_total_usd"] - r["crash_loss_total_usd"]
        breakeven[m] = {"lending_given_up_usd": float(base["avg_loan_capacity_usd"] - r["avg_loan_capacity_usd"]),
                        "revenue_given_up_usd_yr": float(base["spread_revenue_usd_yr"] - r["spread_revenue_usd_yr"]),
                        "revenue_given_up_over_test_usd": float(rev_given_up),
                        "crash_loss_avoided_usd": float(crash_saved),
                        "breakeven_client_failure_share_of_crashes": float(rev_given_up / crash_saved)}

    # margin-period-of-risk sensitivity
    sens = []
    for h in sorted(set(cfg["haircut"]["mpor_sensitivity"] + [H])):
        p = models.build_panel(px, cfg, h, cfg["assets"])
        m = backtest.model_metrics(p, h, conf)[["model", "avg_haircut", "breach_rate", "mean_shortfall_bp"]]
        m["mpor"] = h; sens.append(m)
    sens = pd.concat(sens); sens.to_csv(out / "mpor_sensitivity.csv", index=False)

    # stablecoins, reported separately
    sp = models.build_panel(px, cfg, H, cfg["stablecoins"])
    st = []
    for a, g in sp[sp.in_test].groupby("asset"):
        w = g.loc[g.loss.idxmax()]
        st.append({"asset": a, "days": int(len(g)), "avg_hist1y": float(g.hist1y.mean()), "avg_fhs_floor": float(g.fhs_floor.mean()),
                   "breach_rate_hist1y": float((g.loss > g.hist1y).mean()), "breach_rate_fhs_floor": float((g.loss > g.fhs_floor).mean()),
                   "worst_loss": float(w.loss), "worst_loss_date": str(w.date.date()),
                   "hist1y_on_worst": float(w.hist1y), "fhs_floor_on_worst": float(w.fhs_floor)})
    stable = pd.DataFrame(st); stable.to_csv(out / "stablecoins.csv", index=False)

    # figures
    report.frontier(econ, fig / "lending_vs_crash_loss.png")
    report.btc_history(panel, fig / "btc_haircut_history.png")
    report.breach_by_year(panel, fig / "breaches_by_year.png")
    report.stress_bars(stress, fig / "stress_events.png")
    report.margin_calls(book, fig / "margin_calls.png", cfg["economics"]["margin_call_horizon_days"], cfg["book"]["collateral_usd"])
    report.mpor_chart(sens, fig / "mpor_sensitivity.png")

    t = panel[panel.in_test]
    metrics = {
        "data": {"source": manifest["source"], "commit": manifest["commit"], "licence": manifest["licence"],
                 "downloaded": manifest["downloaded"], "assets": cfg["assets"], "stablecoins": cfg["stablecoins"],
                 "price_days_total": int(dq.days.sum()), "test_start": str(t.date.min().date()),
                 "test_end": str(t.date.max().date()), "asset_days_tested": int(len(t)),
                 "n_assets": int(t.asset.nunique())},
        "settings": {"confidence": conf, "mpor_days": H, "fixed_grid": cfg["haircut"]["fixed_grid"],
                     "economics_illustrative": cfg["economics"], "book_illustrative": cfg["book"]},
        "models": mm.set_index("model").to_dict("index"),
        "book": econ.set_index("model").to_dict("index"),
        "breakeven_vs_baseline": breakeven,
        "halves": halves,
        "stress_events": stress.to_dict("records"),
        "mpor_sensitivity": sens.to_dict("records"),
        "stablecoins": stable.to_dict("records"),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    return metrics


if __name__ == "__main__":
    m = run()
    print(json.dumps({k: {kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()}
                      for k, v in m["book"].items()}, indent=1))
