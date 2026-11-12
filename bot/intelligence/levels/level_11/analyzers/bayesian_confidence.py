"""Bayesian confidence for matured directional recommendations.

Uses a Jeffreys Beta(1/2, 1/2) prior. Closed-trade feedback is deliberately
excluded: it is a different label population and may contain partial exits.
The 95% interval is a normal approximation to the Beta posterior and is
reported as diagnostic evidence only; this analyzer never changes trading.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral, Real

from bot.intelligence.core.models.analysis_result import AnalyzerResult


DEFAULT_PRIOR_ALPHA = 0.5
DEFAULT_PRIOR_BETA = 0.5
DEFAULT_MIN_SAMPLES = 20
_NORMAL_95 = 1.959963984540054


@dataclass(frozen=True)
class BayesianWinRate:
    successes: int
    failures: int
    posterior_alpha: float
    posterior_beta: float
    posterior_mean: float
    posterior_variance: float
    credible_interval_95: tuple[float, float]
    evidence_confidence: float
    ready: bool


def estimate_bayesian_win_rate(
    successes: int,
    failures: int,
    *,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> BayesianWinRate:
    """Return a Beta-Binomial posterior for a binary success rate.

    Success/failure counts are independent matured recommendation outcomes.
    All probabilities are fractions in [0, 1]. A Jeffreys prior avoids
    assigning zero probability after an all-win or all-loss sample.
    """
    for name, value in (("successes", successes), ("failures", failures), ("min_samples", min_samples)):
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError(f"{name} must be an integer")
    if successes < 0 or failures < 0:
        raise ValueError("successes and failures must be non-negative")
    if min_samples < 1:
        raise ValueError("min_samples must be positive")

    for name, value in (("prior_alpha", prior_alpha), ("prior_beta", prior_beta)):
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite positive number")

    alpha = float(prior_alpha) + int(successes)
    beta = float(prior_beta) + int(failures)
    total = alpha + beta
    mean = alpha / total
    variance = alpha * beta / (total * total * (total + 1.0))
    standard_error = math.sqrt(variance)
    lower = max(0.0, mean - _NORMAL_95 * standard_error)
    upper = min(1.0, mean + _NORMAL_95 * standard_error)

    prior_total = float(prior_alpha) + float(prior_beta)
    prior_variance = (
        float(prior_alpha) * float(prior_beta)
        / (prior_total * prior_total * (prior_total + 1.0))
    )
    evidence_confidence = (
        max(0.0, min(1.0, 1.0 - math.sqrt(variance / prior_variance)))
        if prior_variance > 0 else 0.0
    )
    sample_count = int(successes) + int(failures)
    return BayesianWinRate(
        successes=int(successes),
        failures=int(failures),
        posterior_alpha=alpha,
        posterior_beta=beta,
        posterior_mean=mean,
        posterior_variance=variance,
        credible_interval_95=(lower, upper),
        evidence_confidence=evidence_confidence,
        ready=sample_count >= min_samples,
    )


def analyze(observations, *, min_samples: int = DEFAULT_MIN_SAMPLES) -> AnalyzerResult:
    """Estimate confidence from matured forward labels, excluding trade exits."""
    forecast_observations = [
        item for item in observations
        if getattr(item, "realized_trade_return", None) is None
        and isinstance(getattr(item, "correct", None), bool)
    ]
    successes = sum(1 for item in forecast_observations if item.correct)
    failures = len(forecast_observations) - successes
    estimate = estimate_bayesian_win_rate(
        successes, failures, min_samples=min_samples
    )
    warnings = () if estimate.ready else ("bayesian_confidence_insufficient_history",)
    return AnalyzerResult(
        analyzer="bayesian_confidence",
        score=estimate.posterior_mean,
        confidence=estimate.evidence_confidence if estimate.ready else 0.0,
        metrics={
            "sample_count": len(forecast_observations),
            "successes": successes,
            "failures": failures,
            "posterior_alpha": estimate.posterior_alpha,
            "posterior_beta": estimate.posterior_beta,
            "posterior_win_probability": estimate.posterior_mean,
            "posterior_variance": estimate.posterior_variance,
            "credible_interval_95": estimate.credible_interval_95,
            "evidence_confidence": estimate.evidence_confidence,
            "minimum_samples": min_samples,
            "ready": estimate.ready,
            "closed_trade_observations_excluded": sum(
                1 for item in observations
                if getattr(item, "realized_trade_return", None) is not None
            ),
            "shadow_only": True,
            "applied_to_trading": False,
            "credible_interval_method": "normal_approximation_to_beta_posterior",
        },
        warnings=warnings,
    )
