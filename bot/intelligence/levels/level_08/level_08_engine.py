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
        context_warnings = []
        for name, result in (("level3", level3_result), ("level4", level4_result), ("level7", level7_result)):
            if result is None:
                context_warnings.append(f"{name}_context_not_available")
                continue
            if hasattr(result, "symbol"):
                symbol = getattr(result, "symbol")
                if not isinstance(symbol, str) or not symbol:
                    context_warnings.append(f"{name}_symbol_not_available")
                elif symbol != snapshot.symbol:
                    context_warnings.append(f"{name}_symbol_mismatch")

        results = {
            "market_relative_strength": market_relative_strength.analyze(snapshot, level3_result),
            "sector_relative_strength": sector_relative_strength.analyze(snapshot, level3_result),
            "peer_context": peer_context.analyze(snapshot, level4_result),
            "cross_asset_context": cross_asset_context.analyze(snapshot, level3_result),
            "benchmark_alignment": benchmark_alignment.analyze(snapshot, level7_result),
            "relative_consistency": relative_consistency.analyze(level3_result, level7_result),
        }
        effective = {
            key: self.WEIGHTS[key] * max(0.0, min(1.0, results[key].confidence))
            for key in self.WEIGHTS
        }
        total_effective = sum(effective.values())
        score = (
            sum(results[key].score * weight for key, weight in effective.items()) / total_effective
            if total_effective > 0.0 else 0.0
        )
        confidence = sum(self.WEIGHTS[key] * max(0.0, min(1.0, result.confidence)) for key, result in results.items()) / sum(self.WEIGHTS.values())
        consistency = results["relative_consistency"].score
        warnings = list(dict.fromkeys(context_warnings + [w for result in results.values() for w in result.warnings]))
        strengths, weaknesses = [], []
        if not context_warnings and results["market_relative_strength"].score >= 0.7 and results["market_relative_strength"].confidence > 0.0:
            strengths.append("strong_relative_market_strength")
        if not context_warnings and results["relative_consistency"].score >= 0.7 and results["relative_consistency"].confidence > 0.0:
            strengths.append("relative_context_consistent")
        if results["cross_asset_context"].confidence < 0.5:
            weaknesses.append("cross_asset_context_unconfirmed")
        if context_warnings:
            score = 0.0
            confidence = 0.0
            weaknesses.append("invalid_cross_level_context")
        return Level8Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)),
            consistency=max(0.0, min(1.0, consistency)), market_relative_strength=results["market_relative_strength"].score,
            sector_relative_strength=results["sector_relative_strength"].score, peer_context=results["peer_context"].score,
            cross_asset_context=results["cross_asset_context"].score, benchmark_alignment=results["benchmark_alignment"].score,
            relative_consistency=results["relative_consistency"].score, analyzer_results=results,
            strengths=strengths, weaknesses=weaknesses, warnings=warnings,
            metadata={"version": "1.1", "cross_level_context_valid": not context_warnings},
        )
