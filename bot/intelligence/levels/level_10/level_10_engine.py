from __future__ import annotations

import math
from numbers import Real
from typing import Any

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.core.models.analysis_result import AnalyzerResult
from .analyzers import (
    conviction,
    cross_level_agreement,
    confidence_quality,
    risk_adjusted_conviction,
    warning_impact,
    decision_readiness,
)
from .models.level_10_result import Level10Result


class Level10Engine:
    WEIGHTS = {
        "conviction": 0.20,
        "cross_level_agreement": 0.20,
        "confidence_quality": 0.15,
        "risk_adjusted_conviction": 0.20,
        "warning_impact": 0.10,
        "decision_readiness": 0.15,
    }

    REQUIRED_NUMERIC_FIELDS = ("score", "confidence")

    @staticmethod
    def _valid_unit_interval_number(value: Any) -> bool:
        """Reject booleans, non-numbers, non-finite values and values outside [0, 1]."""
        return (
            isinstance(value, Real)
            and not isinstance(value, bool)
            and math.isfinite(value)
            and 0.0 <= value <= 1.0
        )

    @classmethod
    def _validate_inputs(
        cls,
        snapshot: MarketSnapshot,
        level_results: tuple[Any, ...],
    ) -> list[str]:
        warnings: list[str] = []
        expected_symbol = getattr(snapshot, "symbol", None)
        if not isinstance(expected_symbol, str) or not expected_symbol.strip():
            warnings.append("snapshot_symbol_invalid")

        for level, result in zip((5, 6, 7, 8, 9), level_results):
            prefix = f"level{level}"
            if result is None:
                warnings.append(f"{prefix}_result_missing")
                continue

            symbol = getattr(result, "symbol", None)
            if not isinstance(symbol, str) or not symbol.strip():
                warnings.append(f"{prefix}_symbol_invalid")
            elif isinstance(expected_symbol, str) and symbol != expected_symbol:
                warnings.append(f"{prefix}_symbol_mismatch")

            for field in cls.REQUIRED_NUMERIC_FIELDS:
                value = getattr(result, field, None)
                if not cls._valid_unit_interval_number(value):
                    warnings.append(f"{prefix}_{field}_invalid")

        return list(dict.fromkeys(warnings))

    @staticmethod
    def _invalid_input_result(snapshot: MarketSnapshot, warnings: list[str]) -> Level10Result:
        """Return an explicitly non-actionable result without running analyzers."""
        reason_warnings = tuple(warnings)
        analyzer_names = (
            "conviction",
            "cross_level_agreement",
            "confidence_quality",
            "risk_adjusted_conviction",
            "warning_impact",
            "decision_readiness",
        )
        analyzer_results = {
            name: AnalyzerResult(
                analyzer=name,
                score=0.0,
                confidence=0.0,
                metrics={"input_validation_failed": True},
                warnings=reason_warnings,
            )
            for name in analyzer_names
        }
        return Level10Result(
            symbol=getattr(snapshot, "symbol", "") if isinstance(getattr(snapshot, "symbol", ""), str) else "",
            score=0.0,
            confidence=0.0,
            consistency=0.0,
            conviction=0.0,
            cross_level_agreement=0.0,
            confidence_quality=0.0,
            risk_adjusted_conviction=0.0,
            warning_impact=0.0,
            decision_readiness=0.0,
            analyzer_results=analyzer_results,
            strengths=[],
            weaknesses=["invalid_level10_input"],
            warnings=reason_warnings,
            metadata={"version": "1.1", "input_validation_passed": False},
        )

    def analyze(
        self,
        snapshot: MarketSnapshot,
        level5_result,
        level6_result,
        level7_result,
        level8_result,
        level9_result,
    ) -> Level10Result:
        level_results = (
            level5_result,
            level6_result,
            level7_result,
            level8_result,
            level9_result,
        )
        input_warnings = self._validate_inputs(snapshot, level_results)
        if input_warnings:
            return self._invalid_input_result(snapshot, input_warnings)

        results = {
            "conviction": conviction.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
            "cross_level_agreement": cross_level_agreement.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
            "confidence_quality": confidence_quality.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
            "risk_adjusted_conviction": risk_adjusted_conviction.analyze(level5_result, level6_result, level9_result),
            "warning_impact": warning_impact.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
        }
        results["decision_readiness"] = decision_readiness.analyze(*results.values())
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidence = sum(r.confidence for r in results.values()) / len(results)
        consistency = results["cross_level_agreement"].score
        warnings = list(dict.fromkeys(w for r in results.values() for w in r.warnings))
        strengths, weaknesses = [], []
        if results["decision_readiness"].score >= 0.7:
            strengths.append("high_decision_readiness")
        if results["cross_level_agreement"].score >= 0.7:
            strengths.append("strong_cross_level_agreement")
        if results["risk_adjusted_conviction"].score < 0.5:
            weaknesses.append("weak_risk_adjusted_conviction")
        if results["warning_impact"].score < 0.7:
            weaknesses.append("material_warnings")
        return Level10Result(
            symbol=snapshot.symbol,
            score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency,
            conviction=results["conviction"].score,
            cross_level_agreement=results["cross_level_agreement"].score,
            confidence_quality=results["confidence_quality"].score,
            risk_adjusted_conviction=results["risk_adjusted_conviction"].score,
            warning_impact=results["warning_impact"].score,
            decision_readiness=results["decision_readiness"].score,
            analyzer_results=results,
            strengths=strengths,
            weaknesses=weaknesses,
            warnings=warnings,
            metadata={"version": "1.1", "input_validation_passed": True},
        )
