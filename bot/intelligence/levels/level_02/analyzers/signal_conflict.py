from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    # Level 1 scores represent signal strength/favorability, not signed direction.
    # Their spread is therefore only a dispersion proxy, not proof of directional conflict.
    scores = [
        result.score
        for result in level1.analyzer_results
        if result.analyzer != "data_quality" and result.confidence > 0
    ]
    if not scores:
        return AnalyzerResult(
            "signal_conflict",
            0.0,
            0.0,
            {"score_dispersion": None, "directional_conflict_assessed": False},
            ("no_observed_analyzer_results",),
        )
    spread = max(scores) - min(scores)
    consistency = max(0.0, 1.0 - spread)
    return AnalyzerResult(
        "signal_conflict",
        consistency,
        level1.confidence,
        {
            "score_dispersion": spread,
            "consistency_proxy": consistency,
            "directional_conflict_assessed": False,
            "input_analyzers": [
                result.analyzer
                for result in level1.analyzer_results
                if result.analyzer != "data_quality" and result.confidence > 0
            ],
        },
        ("directional_conflict_not_assessed_score_dispersion_only",),
    )
