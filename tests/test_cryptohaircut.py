import numpy as np
import pandas as pd
import pytest

from cryptohaircut import backtest, config, models


@pytest.fixture(scope="module")
def cfg():
    return config.load()


def _prices(n=1500):
    """Real data only: the first n days of the Coin Metrics ETH series (run `make ingest` first)."""
    path = config.ROOT / "data" / "raw" / "eth.csv"
    if not path.exists():
        pytest.skip("run `make ingest` to download the pinned data first")
    d = pd.read_csv(path, usecols=["time", "PriceUSD"]).dropna()
    s = pd.Series(d["PriceUSD"].to_numpy(), index=pd.to_datetime(d["time"]))
    return s.iloc[:n]


def test_no_look_ahead(cfg):
    p = _prices()
    base = models.haircuts_for_asset(p, "zzz", cfg, 2)
    cut = p.index[1000]
    q = p.copy()
    q.loc[q.index > cut] *= np.linspace(0.2, 3.0, (q.index > cut).sum())   # rewrite the future
    alt = models.haircuts_for_asset(q, "zzz", cfg, 2)
    for m in models.MODELS:
        pd.testing.assert_series_equal(base.loc[:cut, m], alt.loc[:cut, m])


def test_loss_is_forward(cfg):
    p = _prices()
    d = models.haircuts_for_asset(p, "zzz", cfg, 2)
    i = 700
    assert d["loss"].iloc[i] == pytest.approx(1 - p.iloc[i + 2] / p.iloc[i])
    assert np.isnan(d["loss"].iloc[-1]) and np.isnan(d["loss"].iloc[-2])


def test_haircut_bounds_and_history_gate(cfg):
    d = models.haircuts_for_asset(_prices(), "zzz", cfg, 2)
    for m in models.MODELS:
        v = d[m].dropna()
        assert (v >= 0).all() and (v <= 1).all()
    assert not d["lendable"].iloc[: cfg["haircut"]["min_history_days"]].any()
    assert (d["fhs_floor"].dropna() >= d["fhs"].dropna().reindex(d["fhs_floor"].dropna().index) - 1e-12).all()


def test_hist_var_matches_quantile(cfg):
    p = _prices()
    d = models.haircuts_for_asset(p, "zzz", cfg, 2)
    t = 900
    lp = np.log(p)
    rh = (lp - lp.shift(2)).iloc[t - 364: t + 1]
    expected = 1 - np.exp(np.quantile(rh, 0.01))
    assert d["hist1y"].iloc[t] == pytest.approx(expected, rel=1e-9)


def test_ewma_recursion():
    r = pd.Series([np.nan] + [0.01] * 40 + [0.1])
    s = models.ewma_vol(r, 0.94, seed_days=30)
    assert s.iloc[-1] == pytest.approx(np.sqrt(0.94 * s.iloc[-2] ** 2 + 0.06 * 0.01))


def test_kupiec():
    lr, p = backtest.kupiec(10000, 100, 0.01)
    assert lr == pytest.approx(0.0, abs=1e-9) and p == pytest.approx(1.0)
    lr, p = backtest.kupiec(10000, 200, 0.01)
    assert p < 1e-6


def test_christoffersen_detects_clustering():
    clustered = [np.array(([0] * 95 + [1] * 5) * 20)]
    lr, p, p11 = backtest.christoffersen(clustered)
    assert p < 0.01 and p11 > 0.5
