from collections import defaultdict

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations) -> AnalyzerResult:
    grouped = defaultdict(list)
    for item in observations:
        if item.regime:
            grouped[str(item.regime)].append(item)

    if not grouped:
        return AnalyzerResult(
            "regime_adaptation", 0.0, 0.0, {},
            ("regime_history_not_available",),
        )

    per_regime = {
        regime: {
            "sample_count": len(items),
            "directional_accuracy": sum(bool(item.correct) for item in items) / len(items),
            "mean_strategy_return": sum(float(item.outcome_return) for item in items) / len(items),
        }
        for regime, items in sorted(grouped.items())
    }
    # Balance regimes equally so a dominant regime does not hide poor performance
    # in less frequent market conditions. This is diagnostic, not live adaptation.
    score = sum(item["directional_accuracy"] for item in per_regime.values()) / len(per_regime)
    sample_count = sum(item["sample_count"] for item in per_regime.values())
    regime_coverage = min(1.0, len(per_regime) / 4.0)
    confidence = min(1.0, sample_count / 20.0) * regime_coverage
    warnings = () if len(per_regime) >= 2 else ("regime_diversity_insufficient",)
    return AnalyzerResult(
        "regime_adaptation",
        max(0.0, min(1.0, score)),
        max(0.0, min(1.0, confidence)),
        {
            "distinct_regimes": len(per_regime),
            "sample_count": sample_count,
            "regime_coverage": regime_coverage,
            "per_regime": per_regime,
            "method": "balanced_regime_directional_accuracy",
            "adaptation_applied": False,
        },
        warnings,
    )
