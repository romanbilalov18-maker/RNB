from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import market_relative_strength, sector_relative_strength, peer_context, cross_asset_context, benchmark_alignment, relative_consistency
from .models.level_08_result import Level8Result


class Level8Engine:
    WEIGHTS = {
        "market_relative_strength": 0.22,
        "sector_relative_strength": 0.14,
        "peer_context": 0.14,
        "cross_asset_context": 0.14,
        "benchmark_alignment": 0.16,
        "relative_consistency": 0.20,
    }

    def analyze(self, snapshot: MarketSnapshot, level3_result, level4_result, level7_result) -> Level8Result:
        results = {
            "market_relative_strength": market_relative_strength.analyze(snapshot, level3_result),
            "sector_relative_strength": sector_relative_strength.analyze(level3_result),
            "peer_context": peer_context.analyze(level4_result),
            "cross_asset_context": cross_asset_context.analyze(level3_result),
            "benchmark_alignment": benchmark_alignment.analyze(snapshot, level7_result),
        }
        results["relative_consistency"] = relative_consistency.analyze(level3_result, level7_result)
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidence = sum(r.confidence for r in results.values()) / len(results)
        consistency = results["relative_consistency"].score
        warnings = list(dict.fromkeys(w for r in results.values() for w in r.warnings))
        strengths, weaknesses = [], []
        if results["market_relative_strength"].score >= 0.7: strengths.append("strong_relative_market_strength")
        if results["relative_consistency"].score >= 0.7: strengths.append("relative_context_consistent")
        if results["cross_asset_context"].confidence < 0.5: weaknesses.append("cross_asset_context_unconfirmed")
        return Level8Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency, market_relative_strength=results["market_relative_strength"].score,
            sector_relative_strength=results["sector_relative_strength"].score, peer_context=results["peer_context"].score,
            cross_asset_context=results["cross_asset_context"].score, benchmark_alignment=results["benchmark_alignment"].score,
            relative_consistency=results["relative_consistency"].score, analyzer_results=results,
            strengths=strengths, weaknesses=weaknesses, warnings=warnings, metadata={"version": "1.0"},
        )
