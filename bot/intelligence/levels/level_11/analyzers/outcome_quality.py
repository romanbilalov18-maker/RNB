from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("outcome_quality", 0.0, 0.0, {"sample_count": 0}, ("learning_history_not_available",))
    correct_ratio = sum(1 for item in observations if item.correct) / len(observations)
    trade_returns = [
        item.realized_trade_return for item in observations
        if getattr(item, "realized_trade_return", None) is not None
    ]
    metrics = {
        "sample_count": len(observations),
        "forecast_directional_accuracy": correct_ratio,
        "realized_trade_count": len(trade_returns),
        "realized_trade_win_rate": (
            sum(value > 0 for value in trade_returns) / len(trade_returns)
            if trade_returns else None
        ),
        "mean_realized_trade_return": (
            sum(trade_returns) / len(trade_returns) if trade_returns else None
        ),
        "trade_pnl_is_separate_from_forecast_label": True,
    }
    return AnalyzerResult(
        "outcome_quality", correct_ratio, min(1.0, len(observations) / 20.0), metrics
    )
