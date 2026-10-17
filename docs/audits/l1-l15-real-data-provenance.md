# L1–L15 real-data provenance audit

## Scope and safety boundary

The production scan path reads market data from T-Invest. This audit does not introduce generated market observations, a fabricated portfolio, or broker order submission. The dedicated smoke runner is read-only. The main bot's execution path is virtual (PaperExecutor) and uses the existing persisted virtual portfolio.

## Data path

1. LiveMarketRunner requests the tradable RUB-share universe, last prices, previous close prices, daily candles, and instrument metadata from T-Invest.
2. It builds the current scan and historical candle collections. It also requests T-Invest trading statuses for the instruments being analyzed.
3. Order-book spread is considered only when T-Invest reports an active trading phase. When the book, tick size, or active status is unavailable, liquidity stays unknown.
4. build_market_snapshot passes observed values and explicit missingness into MarketSnapshot.
5. IntelligencePipeline.analyze calls L1 through L15 in sequence. The pipeline has no trade side effects.
6. The main bot sends valid results through DecisionEngine and the existing virtual PaperExecutor. The read-only smoke runner does not execute trades.

## Level-by-level handoff matrix

| Level | Inputs and role | Missing-data behavior / boundary |
|---|---|---|
| L1 — market facts | Current price, previous close, candle volume, volatility, momentum, and the observed top-of-book spread proxy | Missing liquidity is unknown with zero confidence; spread proxy identifies its source and does not claim to measure full depth |
| L2 — price/trend structure | MarketSnapshot and L1 evidence | Analyzer confidence determines effective contribution; unavailable evidence is not promoted to confident evidence |
| L3 — market context | Observed market breadth/return, sector and peer returns, aligned historical return series, correlation context | Official macroeconomic indicators are not provided by this T-Invest scan and remain explicitly unavailable; observed breadth is not labelled as an official macro feed |
| L4 — activity/pressure | Candle OHLCV, volume ratios, and the available liquidity proxy | Partial buying/selling/abnormal-activity inputs produce warnings; volume ratio is not substituted for order-book liquidity |
| L5 — signal quality | L2, L3, and L4 outputs | Cross-level symbol/context problems invalidate the aggregate rather than silently accepting mismatched results |
| L6 — risk | Snapshot history and L5 context; downside, volatility, reward/risk, and adverse scenarios | Required evidence and confidence gate the contribution; risk severity is inverted where the aggregate means “higher is better” |
| L7 — temporal behavior | Historical snapshot series and L3–L6 context | Sparse history reduces confidence and generates warnings |
| L8 — relative performance | Leave-one-out market basket, sector/peer context, aligned cross-asset history | Does not fall back to a market return that includes the target instrument; relative strength requires a sufficient observed peer sample |
| L9 — portfolio | Snapshot holdings and market values, plus L5/L6/L8 | A missing portfolio is different from a confirmed empty portfolio. The main bot passes its persisted virtual portfolio; the read-only smoke runner passes no portfolio and must not invent a balance |
| L10 — decision readiness | L5–L9 metrics and warnings | Validates symbols, required numeric values, and warning collections before aggregation |
| L11 — learning | Matured observations from the decision-audit store, including saved L1–L15 snapshots and realized virtual SELL outcomes | No observations means no learned evidence. Weight adaptation is a shadow proposal only; weights are not automatically applied to trading |
| L12 — anomalies | Real candle history and L4/L7/L10 context | Unavailable OHLCV or upstream evidence remains unavailable and lowers confidence |
| L13 — scenarios | L6/L7/L10/L12 | Scenario forecasts are derived from upstream evidence and explicitly marked probabilistic; they do not execute trades |
| L14 — contradictions | L6/L10/L12/L13 plus data-reliability checks | Reliability gates confidence; it is not treated as a contradiction signal itself |
| L15 — final synthesis | L6/L10/L11/L12/L13/L14 | Final result inherits upstream warnings and quality limits; it does not submit orders |

## Confirmed fixes in this PR

- Removed the diagnostic VirtualPortfolio(initial_balance=10_000.0) from the read-only T-Invest runner. It now passes portfolio=None and reports portfolio context as unavailable.
- Removed the fallback lot size of one when T-Invest instrument metadata is missing. Virtual buys are skipped unless the actual price and lot size are present and valid.
- Corrected L8 context availability so it is true only when observed leave-one-out peers exist. L8 no longer falls back to a benchmark containing the analyzed instrument.
- Added real T-Invest order-book retrieval for analyzed instruments. The normalized liquidity value is a transparent top-of-book spread proxy: 1 / max(1, spread_in_ticks). It is only used in an active trading phase and is not represented as full order-book depth.
- Added a trading-session guard to the main virtual execution path. If T-Invest reports no active instruments, the bot skips virtual trades, portfolio writes, and decision-audit observations. This prevents repeated out-of-session quotes from being recorded as fresh L11 training decisions.
- Restricted virtual position management and candidate sizing to instruments T-Invest reports as actively trading.

## Explicitly unavailable / not fabricated

- Official macroeconomic indicators are not present in the market scan. The analyzer reports this instead of generating macro values.
- When the market is closed, or T-Invest does not return a valid active-session order book and tick size, liquidity remains unknown. A closed-session smoke test cannot prove the active-session order-book path; verify that path during an actual trading session.
- The read-only smoke runner does not load the bot's persistent local virtual portfolio. Portfolio-sensitive L9 evidence therefore remains unavailable in that runner rather than being filled with a made-up balance.
- The read-only market monitor reports that the Decision Engine is not connected because it is a monitoring-only path. The main bot has a separate DecisionEngine → PaperExecutor virtual path.

## Verification approach

The PR runs the existing unit and Intelligence Pipeline checks plus a read-only smoke run against actual T-Invest data. Unit fixtures validate isolated logic; they are not used as production market inputs. No broker orders are submitted, and L11 shadow weights are not activated.
