# How Much Should You Lend Against Crypto? Testing Collateral Haircuts on Eight Years of Crashes

> Companion repos: [treasury-curve-hedging](https://github.com/guptagaurav-info/treasury-curve-hedging) · [cmbs-distress-early-warning](https://github.com/guptagaurav-info/cmbs-distress-early-warning) · [smb-credit-pd-lgd](https://github.com/guptagaurav-info/smb-credit-pd-lgd). Author: Gaurav Gupta.

A walk-forward test of the haircut a prime broker, bank or crypto lender should apply to digital-asset collateral, built on Coin Metrics' free daily reference prices for 17 coins from 2018 to May 2026. It answers the question a credit committee asks before it lends against bitcoin, ether and altcoins: **how much can we advance per dollar of collateral, and what do we lose if a client fails in the next crash?**

```bash
pip install -r requirements.txt
make ingest       # download the pinned Coin Metrics CSVs and record sha256 (reports/data_manifest.json)
make all          # haircuts -> walk-forward validation -> stress events -> reports/ and figures
make test         # unit tests on the real data: no look-ahead, forward-loss alignment, VaR maths, backtests
```

**How it works:** flowcharts of the pipeline, the daily haircut decision and a proposed production design are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Data

- **What:** daily end-of-day USD reference price (`PriceUSD`) for 17 crypto assets and two stablecoins, from the Coin Metrics Community data archive ([github.com/coinmetrics/data](https://github.com/coinmetrics/data)), produced from the free Community tier of the Coin Metrics API.
- **Copy used:** `csv/<asset>.csv` at commit `f1a36afb962731c387bb03982758ab0103063da5`, downloaded 2026-10-22. The archive's latest price at that commit is 23 May 2026. sha256 of every file is in `reports/data_manifest.json`; `ingest.py` stops if the bytes change.
- **Licence:** CC BY-NC 4.0 (Coin Metrics). The data is not redistributed here; `data/raw/` is git-ignored and re-downloaded by `make ingest`.
- **Assets:** BTC, ETH, XRP, BNB, DOGE, ADA, TRX, LINK, LTC, BCH, XLM, ETC, ALGO, DOT, UNI, AAVE and MATIC (kept until its series ends in October 2025, to avoid survivorship bias), plus USDT and USDC reported separately. 64,584 daily prices; no missing days inside any series (`reports/data_quality.csv`).

## The question as a position

- **Loan:** a client pledges crypto; the lender advances (1 − haircut) per $1 of collateral marked at the day's close.
- **Breach:** the client fails and the collateral is sold two days later (the margin period of risk). If the price has fallen by more than the haircut, the lender is left with an uncovered loss.
- **Book (illustrative):** $1bn of collateral, 50% BTC, 25% ETH, 25% split equally across the other coins that are lendable that day, cross-margined.

## Haircut rules compared

| Rule | What it does | Uses |
|---|---|---|
| Static grid (illustrative) | 20% BTC, 25% ETH, 40% everything else | Nothing to fit |
| **1-year historical VaR (baseline)** | 1st percentile of 2-day returns over the trailing year | Trailing 365 days |
| Volatility-scaled (EWMA FHS) | Filtered historical simulation: 3 years of 2-day returns standardised by EWMA volatility (λ 0.94), rescaled to today's volatility | Trailing 3 years |
| **Volatility-scaled + 10-year floor** | The same, never below the 1st percentile of 2-day returns over up to ten years of the coin's own history (an EMIR-style anti-procyclicality lookback) | Up to 10 years |

All rules target 99% confidence over a two-day close-out. Every haircut on day t uses prices up to and including day t only; the loss it is scored against runs from t to t + 2 (asserted in a unit test that rewrites future prices and checks that no earlier haircut changes). A coin becomes lendable after 365 days of history. Test: 1 January 2018 to 21 May 2026, 44,497 coin-days.

## Results (walk-forward, out of sample)

| Rule | Average haircut | Breach rate (target 1%) | Kupiec p | Worst coin shortfall | Max 5-day haircut jump |
|---|---|---|---|---|---|
| Static grid | 37.6% | 0.04% | 0.00 (too few) | 20.1% | 0 |
| 1-year historical VaR | 16.4% | 1.18% | 0.07 | 34.0% | 6.5 pts |
| Volatility-scaled | 16.5% | 1.15% | 0.09 | 34.1% | 44.1 pts |
| **Volatility-scaled + floor** | **21.8%** | **0.30%** | 0.00 (too few) | **28.8%** | 44.1 pts |

Breach rates use all coin-days; Kupiec tests use 22,255 non-overlapping two-day windows. The volatility-scaled rule's breaches cluster (Christoffersen independence p = 0.018); the others do not.

### Illustrative $1bn collateral book

| Rule | Average lent | Spread revenue at 4% | Uncovered loss if the client fails at each of six crash dates | Worst single uncovered loss | Peak 5-day margin call |
|---|---|---|---|---|---|
| Static grid | $738M | $29.5M/yr | $25.8M (1 of 6 crashes) | $136.9M | $0 |
| 1-year historical VaR | $860M | $34.4M/yr | $300.9M (5 of 6) | $258.3M | $18.0M |
| Volatility-scaled | $852M | $34.1M/yr | $321.7M (4 of 6) | $230.1M | $288.5M |
| **Volatility-scaled + floor** | **$805M** | **$32.2M/yr** | **$164.7M (2 of 6)** | **$193.6M** | $241.8M |

Crash dates (fixed in `configs/config.yaml` before results were run): 11 Mar 2020, 18 May 2021, 12 Jun 2022, 7 Nov 2022, 3 Aug 2024, 9 Oct 2025. The worst single two-day window for every rule was 10–12 March 2020, when the book lost 39.9%.

### Findings I would raise with a credit committee

1. **A haircut that passes its backtest can still fail the crash.** The 1-year VaR hits its 1% target (Kupiec p = 0.07) and still left $300.9M uncovered across the six crashes, because its breaches are rare but large: on 7 November 2022 (FTX) it held 15.2% against a 26.2% book loss.
2. **Volatility scaling reacts after the damage.** Going into FTX the volatility-scaled haircut had fallen to 11.2%, below the baseline; it then demanded up to $288.5M of extra collateral in five days in March 2020, exactly when clients have least to give.
3. **A long-memory floor is the cheapest protection tested.** Against the baseline, the floor gives up $54.9M of lending ($2.2M a year at 4%, illustrative) and avoids $136.2M of crash loss. It pays for itself if a client fails in more than about one crash in seven (13.5%).
4. **The static grid was the best crash protection, at the highest price.** It lent $122.9M less than the baseline ($41.2M of spread over the test, illustrative) and lost $25.8M across the crashes. Its break-even is 15.0% of crashes.
5. **Stablecoins are not cash.** USDC's one-year haircut on 9 March 2023 was 0.08%; it lost 2.9% over the next two days.
6. **The close-out assumption drives the answer.** Moving from 2 to 5 days of close-out raises the floor rule's average haircut from 21.8% to 31.9%; the baseline's breach rate rises from 1.18% to 1.25%, and to 1.67% at 10 days.

## What this does not show

- Daily end-of-day reference prices: no intraday lows, order-book depth or liquidation slippage. Real close-out losses in a cascade are likely worse.
- Single-asset and simple basket positions; no client-level portfolio margining, concentration add-ons, wrong-way exposure to the client's own token, or exchange/custody risk.
- Revenue and break-even figures use an assumed 4% lending spread and are illustrative.
- Independent research on public data. Not deployed, not investment or lending advice.

## Repo layout

```
configs/config.yaml          every choice, fixed before results were examined; data commit, crash dates
src/cryptohaircut/ingest.py  download + sha256 manifest; tidy daily price panel; data-quality report
src/cryptohaircut/models.py  the four haircut rules and the forward two-day loss (no look-ahead)
src/cryptohaircut/backtest.py Kupiec, Christoffersen, shortfall, procyclicality, book economics
src/cryptohaircut/report.py  figures
src/cryptohaircut/pipeline.py end to end -> reports/
tests/                       look-ahead, alignment, VaR maths, EWMA, backtest statistics (real data)
reports/metrics.json         every number quoted in the article
```

## Data and citations

- Coin Metrics. *Coin Metrics Community Data* (daily `PriceUSD`). [github.com/coinmetrics/data](https://github.com/coinmetrics/data), CC BY-NC 4.0, commit f1a36af.
- J.P. Morgan/Reuters (1996). *RiskMetrics — Technical Document*, 4th ed. (EWMA volatility, λ = 0.94).
- Barone-Adesi, G., Giannopoulos, K. and Vosper, L. (1999). "VaR without correlations for portfolios of derivative securities." *Journal of Futures Markets*, 19(5), 583-602. (Filtered historical simulation.)
- Kupiec, P. (1995). "Techniques for verifying the accuracy of risk measurement models." *Journal of Derivatives*, 3(2), 73-84.
- Christoffersen, P. (1998). "Evaluating interval forecasts." *International Economic Review*, 39(4), 841-862.
- Commission Delegated Regulation (EU) No 153/2013, Article 28 (anti-procyclicality margin measures for CCPs, including the ten-year lookback option).

Code, analysis, charts and text were produced with AI assistance (Claude, by Anthropic) and reviewed by Gaurav Gupta. MIT licence (code only; the data keeps its own licence).
