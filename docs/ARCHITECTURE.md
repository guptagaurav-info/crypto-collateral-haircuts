# How this project works

Three diagrams:
1. **Pipeline**: every step, its source file, and the logic inside it.
2. **Daily haircut decision**: how one margin date becomes a haircut, an advance and a scored outcome.
3. **Production design**: how the same logic would run as a daily collateral-risk process. This is a proposed design and is not implemented in this repo.

Colour key: **blue** = external data source · **lavender** = code step (file named in the box) · **yellow** = model · **red** = check or gate · **grey** = output

## 1. Pipeline (what `make all` runs)

```mermaid
flowchart TD
    SRC["SOURCE: Coin Metrics Community data<br/>daily PriceUSD, 17 coins + USDT, USDC<br/>github.com/coinmetrics/data @ f1a36af"]

    subgraph S0["Stage 0 · Ingest (ingest.py)"]
      I1{"sha256 matches<br/>reports/data_manifest.json?"}
      I1 -- "no" --> IX["Stop: source changed"]
      I1 -- "yes" --> I2["Daily panel, one column per coin<br/>data_quality.csv: 64,584 prices, no gaps"]
    end

    subgraph S1["Stage 1 · Haircut rules (models.py)"]
      G0{"Lendable? at least 365 days of history"}
      G0 --> M0["Static grid: 20% BTC, 25% ETH, 40% others"]
      G0 --> M1["1-year historical VaR (baseline)"]
      G0 --> M2["Volatility-scaled: EWMA filtered historical simulation"]
      G0 --> M3["Volatility-scaled + 10-year floor"]
    end

    subgraph S2["Stage 2 · Outcome (models.py)"]
      L1["Forward 2-day loss: 1 - P(t+2) / P(t)<br/>prices after t never enter the haircut (unit-tested)"]
    end

    subgraph S3["Stage 3 · Validation (backtest.py, pipeline.py)"]
      V1["Breach rate vs 1% target, Kupiec and Christoffersen tests<br/>on 22,255 non-overlapping windows"]
      V2["Shortfall beyond the haircut, 5-day haircut jumps,<br/>split halves, 1/2/5/10-day close-out"]
      V3["Illustrative $1bn book: lending, crash-date losses,<br/>margin calls, break-even vs baseline"]
    end

    OUT["reports/metrics.json · model_metrics.csv · book_economics.csv<br/>stress_events.csv · stablecoins.csv · figures/*.png"]

    SRC --> S0 --> S1 --> S2 --> S3 --> OUT
    classDef src fill:#dbe8ff,stroke:#1f5fbf,color:#0b1f44
    classDef model fill:#fff3c4,stroke:#b7791f,color:#3d2a00
    classDef gate fill:#fde2e1,stroke:#b03a2e,color:#4a0f0a
    classDef out fill:#eeeeee,stroke:#777,color:#222
    classDef step fill:#ece8ff,stroke:#6b5fbf,color:#1e1846
    class SRC src
    class M0,M1,M2,M3 model
    class I1,G0,IX gate
    class OUT out
    class I2,L1,V1,V2,V3 step
```

## 2. Daily haircut decision

```mermaid
flowchart TD
    A["Margin date t<br/>collateral marked at the day-t reference price"] --> B["History up to and including t<br/>2-day returns and EWMA volatility"]
    B --> C["Volatility-scaled haircut<br/>1st percentile of standardised 2-day returns x today's vol"]
    B --> D["Floor<br/>1st percentile of 2-day returns over up to 10 years"]
    C & D --> E["Haircut = max(volatility-scaled, floor)"]
    E --> F["Advance = (1 - haircut) x collateral value"]
    F --> G{"Client fails: sell at t + 2"}
    G -- "loss <= haircut" --> H["Covered"]
    G -- "loss > haircut" --> I["Uncovered loss = (loss - haircut) x collateral"]
    E --> J{"Controls"}
    J --> J1["5-day haircut jump vs call-size limit"]
    J --> J2["Book stress loss at a 40% two-day move vs appetite"]
    J --> J3["Breach count vs 1% target, monthly"]
    classDef model fill:#fff3c4,stroke:#b7791f,color:#3d2a00
    classDef gate fill:#fde2e1,stroke:#b03a2e,color:#4a0f0a
    class C,D,E model
    class G,J gate
```

## 3. Production design (proposed, not implemented)

```mermaid
flowchart TD
    P1["Reference prices from two or more independent sources<br/>(index provider + exchange composite)"] --> P2{"Data checks:<br/>staleness, source divergence > 2%, jumps > 5 sd"}
    P2 --> P3["Haircut engine: champion = volatility-scaled + floor<br/>challengers = 1-year VaR, static grid"]
    P3 --> P4["Add-ons: concentration vs average daily volume,<br/>client's own token, custody venue"]
    P4 --> P5["Margin calls: phase in increases over 3 days<br/>unless the book stress limit is breached"]
    P5 --> P6["Daily report: advances, haircuts, stress loss at -40% in 2 days"]
    P6 --> P7{"Monthly model review"}
    P7 --> P8["Breach count, shortfall, call sizes vs limits<br/>escalate to credit committee"]
    classDef gate fill:#fde2e1,stroke:#b03a2e,color:#4a0f0a
    classDef model fill:#fff3c4,stroke:#b7791f,color:#3d2a00
    class P2,P7 gate
    class P3 model
```
