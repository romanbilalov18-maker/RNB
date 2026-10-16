from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import number, result_or_unavailable


def analyze(snapshot, level5_result) -> AnalyzerResult:
    raw_returns = getattr(snapshot, "historical_returns", None)
    if raw_returns is None:
        return result_or_unavailable("reward_potential", ["historical_returns_not_available"])
    returns = []
    invalid_count = 0
    try:
        for raw in raw_returns:
            value = number(raw)
            if value is None:
                invalid_count += 1
            else:
                returns.append(value)
    except TypeError:
        return result_or_unavailable("reward_potential", ["historical_returns_invalid"])
    positive = sorted(value for value in returns if value > 0)
    warnings = ["historical_returns_invalid_observations"] if invalid_count else []
    if len(returns) < 10 or not positive:
        return result_or_unavailable("reward_potential", warnings + ["historical_upside_distribution_insufficient"], {
            "observations": len(returns), "invalid_observations": invalid_count,
            "positive_return_observations": len(positive),
        })
    index = min(len(positive) - 1, int(0.9 * (len(positive) - 1)))
    upside_quantile = positive[index]
    score = min(1.0, upside_quantile / 0.05)
    confidence = min(1.0, len(returns) / 30.0) * (len(returns) / (len(returns) + invalid_count))
    return AnalyzerResult("reward_potential", score, confidence, {
        "historical_positive_return_p90": upside_quantile, "observations": len(returns),
        "invalid_observations": invalid_count, "method": "empirical_positive_return_quantile",
    }, tuple(warnings))
