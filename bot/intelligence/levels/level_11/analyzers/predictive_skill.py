from __future__ import annotations

from math import sqrt


MIN_PROPOSAL_SAMPLES = 20
MIN_FEATURE_SAMPLES = 20


def feature_predictive_metrics(observations, attribute: str) -> dict[str, dict]:
    """Measure whether high historical scores align with correct outcomes."""
    names = sorted({
        name
        for observation in observations
        for name in getattr(observation, attribute, {})
    })
    metrics: dict[str, dict] = {}
    for name in names:
        pairs = [
            (float(getattr(observation, attribute)[name]), float(bool(observation.correct)))
            for observation in observations
            if name in getattr(observation, attribute, {})
        ]
        count = len(pairs)
        if count < 2:
            continue
        x_mean = sum(x for x, _ in pairs) / count
        y_mean = sum(y for _, y in pairs) / count
        covariance = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
        x_var = sum((x - x_mean) ** 2 for x, _ in pairs)
        y_var = sum((y - y_mean) ** 2 for _, y in pairs)
        correlation = covariance / sqrt(x_var * y_var) if x_var > 0 and y_var > 0 else 0.0
        correlation = max(-1.0, min(1.0, correlation))
        metrics[name] = {
            "sample_count": count,
            "correlation_with_correct_outcome": correlation,
            "effectiveness": max(0.0, min(1.0, 0.5 + 0.5 * correlation)),
        }
    return metrics


def proposed_weights(metrics: dict[str, dict], total_observations: int) -> dict[str, float]:
    """Create a conservative shadow proposal; never apply it to trade decisions."""
    eligible = {
        name: max(0.0, metric["correlation_with_correct_outcome"])
        for name, metric in metrics.items()
        if metric["sample_count"] >= MIN_FEATURE_SAMPLES
    }
    if total_observations < MIN_PROPOSAL_SAMPLES or not eligible:
        return {}
    skill_total = sum(eligible.values())
    if skill_total <= 1e-12:
        return {}
    names = sorted(eligible)
    equal = 1.0 / len(names)
    weights = {
        name: 0.5 * equal + 0.5 * eligible[name] / skill_total
        for name in names
    }
    total = sum(weights.values())
    return {name: value / total for name, value in weights.items()}


def effectiveness_score(metrics: dict[str, dict]) -> float:
    if not metrics:
        return 0.5
    return sum(item["effectiveness"] for item in metrics.values()) / len(metrics)
