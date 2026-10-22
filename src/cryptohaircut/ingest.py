"""Download pinned Coin Metrics CSVs, record sha256, build a tidy daily price panel."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import pandas as pd

from .config import load, ROOT

MANIFEST = "reports/data_manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(cfg: dict) -> dict:
    raw = ROOT / cfg["raw_dir"]
    raw.mkdir(parents=True, exist_ok=True)
    src = cfg["source"]
    manifest_path = ROOT / MANIFEST
    pinned = json.loads(manifest_path.read_text())["files"] if manifest_path.exists() else {}
    files = {}
    for asset in cfg["assets"] + cfg["stablecoins"]:
        url = src["url_template"].format(commit=src["commit"], asset=asset)
        dest = raw / f"{asset}.csv"
        if not dest.exists():
            urllib.request.urlretrieve(url, dest)
        digest = _sha256(dest)
        if asset in pinned and pinned[asset]["sha256"] != digest:
            raise RuntimeError(f"{asset}: sha256 changed ({digest} vs pinned {pinned[asset]['sha256']})")
        files[asset] = {"url": url, "sha256": digest, "bytes": dest.stat().st_size}
    manifest = {"source": src["repo"], "commit": src["commit"], "licence": src["licence"],
                "downloaded": src["downloaded"], "field": src["field"], "files": files}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest


def load_prices(cfg: dict) -> pd.DataFrame:
    """Wide frame: index = UTC date, columns = asset, values = PriceUSD. Gaps stay NaN."""
    raw = ROOT / cfg["raw_dir"]
    field = cfg["source"]["field"]
    cols = {}
    for asset in cfg["assets"] + cfg["stablecoins"]:
        d = pd.read_csv(raw / f"{asset}.csv", usecols=["time", field])
        d["time"] = pd.to_datetime(d["time"])
        s = d.set_index("time")[field].astype(float)
        s = s[s > 0].dropna()
        cols[asset] = s
    px = pd.DataFrame(cols).sort_index()
    px = px.loc[: cfg["test"]["end"]]
    full = pd.date_range(px.index.min(), px.index.max(), freq="D")
    return px.reindex(full)


def data_quality(px: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for a in px.columns:
        s = px[a]
        first, last = s.first_valid_index(), s.last_valid_index()
        inside = s.loc[first:last]
        r = inside.pct_change(fill_method=None)
        rows.append({"asset": a, "first": first.date(), "last": last.date(), "days": int(inside.notna().sum()),
                     "missing_inside": int(inside.isna().sum()),
                     "worst_day_pct": round(100 * r.min(), 1), "best_day_pct": round(100 * r.max(), 1)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    c = load()
    m = download(c)
    print(json.dumps({k: v["sha256"][:12] for k, v in m["files"].items()}, indent=1))
