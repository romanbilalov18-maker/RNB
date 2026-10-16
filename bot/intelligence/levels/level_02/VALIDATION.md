# Level 2 validation notes

## Contract with Level 1

Level 2 consumes the same MarketSnapshot plus the Level1Result. It must preserve missingness: an unavailable or zero-confidence Level 1 analyzer is not evidence of a negative market signal.

- Trend uses the fractional momentum mapping `0.5 + momentum * 5`, matching Level 1's momentum analyzer, and combines it with Level 1's price score.
- Momentum structure compares `MarketSnapshot.price_change()` and `MarketSnapshot.momentum`. Both are expected to be fractional returns on the same horizon. If the upstream producer changes units or horizons, this calculation must be revised; raw inputs and their difference are exposed in metrics.
- Price structure combines Level 1 price score with observed price-change direction.
- Volume flow requires a confident Level 1 volume result and a valid observed current-to-average volume ratio. Missing ratio data yields zero confidence.
- Relative strength uses `relative_market_return` only when the snapshot explicitly marks that context available and provides a positive sample count. It does not substitute momentum or liquidity.
- Signal conflict currently measures dispersion between Level 1 scores. It does not infer signed direction from these scores and must not be interpreted as a true directional-conflict detector.

## Known limitations

- Trend and price-structure analyses are simplified, not multi-candle trend/market-structure recognition.
- Momentum alignment assumes same-unit, same-horizon fractional returns; the current model does not carry an explicit horizon/unit tag.
- Relative strength uses the sign of relative return as its score; magnitude remains in metrics and is not normalized for volatility or horizon.
- Signal-conflict output is a score-dispersion proxy, not directional disagreement.
- These are code-contract and unit-test notes, not evidence of predictive value or profitability. No real-market performance test is part of this validation stage.
