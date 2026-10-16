import math
from bot.intelligence.core.models.analysis_result import AnalyzerResult


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def analyze(snapshot, level4_result) -> AnalyzerResult:
    peer_return = getattr(snapshot, "peer_return", None)
    peer_count = getattr(snapshot, "peer_count", None)
    if not _finite(peer_return) or not isinstance(peer_count, int) or isinstance(peer_count, bool) or peer_count < 2:
        return AnalyzerResult("peer_context", 0.0, 0.0, {"peer_count": peer_count}, ("peer_universe_not_available",))
    change = snapshot.price_change()
    if not _finite(change):
        return AnalyzerResult("peer_context", 0.0, 0.0, {"peer_return": peer_return}, ("asset_return_not_available",))
    relative = change - peer_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    return AnalyzerResult("peer_context", score, min(1.0, peer_count / 10.0), {"asset_return": change, "peer_return": peer_return, "relative_return": relative, "peer_count": peer_count})
