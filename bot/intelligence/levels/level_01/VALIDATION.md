# Level 1 historical validation

This is a standalone diagnostic for Level 1. It does not invoke the trading engine, place orders, or connect Level 1 to other intelligence levels.

## Fast checks

The dedicated workflow runs the Level 1 contract tests and tests for the validation harness on pull requests and pushes affecting Level 1.

## Historical check with real data

The historical workflow requires a real OHLCV CSV committed to the repository. It does not generate substitute market data or download data silently.

Required header:

```csv
timestamp,symbol,close,volume
2026-01-01,AAA,100.25,120000
2026-01-02,AAA,101.10,135000
```

Use one row per symbol and candle, with a consistent candle interval and chronological timestamps. Include enough rows per symbol: more than `window + horizon` (defaults: 20 + 5).

In GitHub, open **Actions → Level 1 Validation → Run workflow**, enter the path to the committed CSV, then choose lookback window and forward horizon. Download the `level-01-historical-report` artifact.

## Interpretation

The report contains the score-to-forward-return correlation, mean forward return in the highest and lowest score quartiles, and per-analyzer availability diagnostics. These are diagnostic statistics, not proof of profitable predictions. The test does not include fees, spread, slippage, statistical significance, or session-specific analysis. Do not use it alone to enable live trading.

The CSV's `close` and `volume` must be adjusted/consistent with the instrument and candle interval. Verify the live producer's volatility and momentum units before interpreting historical results.
