# RNB Intelligence

This package contains additive intelligence modules for the trading bot.

## Principles

- Improve decision quality without replacing the existing trading engine.
- Keep BUY/SELL execution, portfolio persistence, TP/SL, and position sizing backward-compatible.
- Add new signals and filters incrementally.
- Every new decision factor must be covered by tests before it affects trading decisions.

## Planned modules

- signal_quality.py — quality scoring for trading signals.
- market_context.py — broader market context.
- signal_filters.py — filters for weak or conflicting setups.
- decision_context.py — combines existing and new evidence without changing execution.
