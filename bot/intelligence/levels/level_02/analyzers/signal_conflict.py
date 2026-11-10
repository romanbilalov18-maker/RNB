from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


# These inputs describe execution/risk conditions, not directional attractiveness.
# Mixing them into alpha-score dispersion makes a safe/unsafe asset look like a
# conflicting market signal, even when price/momentum/volume agree.
NON_ALPHA_ANALYZERS = frozenset({"data_quality", "volatility", "liquidity"})


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    # Level 1 scores represent favorability, not signed direction. Their spread
    # is only a consistency proxy; it is not a directional-conflict detector.
    alpha_results = [
        result
        for result in level1.analyzer_results
        if result.analyzer not in NON_ALPHA_ANALYZERS and result.confidence > 0
    ]
    if not alpha_results:
        return AnalyzerResult(
            "signal_conflict",
            0.0,
            0.0,
            {
                "score_dispersion": None,
                "directional_conflict_assessed": False,
                "input_analyzers": [],
                "excluded_non_alpha_analyzers": sorted(NON_ALPHA_ANALYZERS),
            },
            ("no_observed_alpha_analyzer_results",),
        )
    scores = [result.score for result in alpha_results]
    spread = max(scores) - min(scores)
    consistency = max(0.0, 1.0 - spread)
    confidence = sum(result.confidence for result in alpha_results) / len(alpha_results)
    return AnalyzerResult(
        "signal_conflict",
        consistency,
        confidence,
        {
            "score_dispersion": spread,
            "consistency_proxy": consistency,
            "directional_conflict_assessed": False,
            "input_analyzers": [result.analyzer for result in alpha_results],
            "excluded_non_alpha_analyzers": sorted(NON_ALPHA_ANALYZERS),
        },
        ("directional_conflict_not_assessed_score_dispersion_only",),
    )
