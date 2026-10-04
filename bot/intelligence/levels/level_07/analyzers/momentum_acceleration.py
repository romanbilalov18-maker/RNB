from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level6_result) -> AnalyzerResult:
    momentum = snapshot.momentum
    acceleration = momentum - snapshot.price_change()
    score = min(1.0, max(0.0, 0.5 + acceleration * 8.0))
    return AnalyzerResult("momentum_acceleration", score, level6_result.confidence, {"momentum": momentum, "acceleration_proxy": acceleration})
