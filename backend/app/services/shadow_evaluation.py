"""Évaluation shadow automatique et sans effet sur la production."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.candles import Candle
from app.domain.signal_evaluation import evaluate_signal_snapshot
from app.models.backtest import SignalObservation
from app.models.experiment import ProfileStatus, ShadowComparison
from app.repositories.experiment_repository import ExperimentRepository


class ShadowEvaluationService:
    def __init__(self, repository: ExperimentRepository) -> None:
        self.repository = repository

    async def evaluate_closed_candle(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: Sequence[Candle],
    ) -> int:
        """Compare production et profils shadow sur la même information causale."""
        if not candles or candles[-1].close_time is None:
            return 0
        profiles = await self.repository.profiles()
        production = next(
            (item for item in profiles if item.status == ProfileStatus.PRODUCTION), None
        )
        candidates = [
            item
            for item in profiles
            if item.status == ProfileStatus.SHADOW and item.signal_config.timeframe == timeframe
        ]
        if production is None or production.signal_config.timeframe != timeframe:
            return 0
        decision_time = candles[-1].close_time
        trend: dict[str, Sequence[Candle]] = {timeframe: candles}
        reference = evaluate_signal_snapshot(
            job_id="shadow",
            symbol=symbol,
            decision_time_ms=decision_time,
            primary=candles,
            trend_candles=trend,
            profile=production.signal_config,
            dataset_version=f"live:{candles[-1].open_time}",
            profile_id=production.id,
        )
        written = 0
        for candidate in candidates:
            challenger = evaluate_signal_snapshot(
                job_id="shadow",
                symbol=symbol,
                decision_time_ms=decision_time,
                primary=candles,
                trend_candles=trend,
                profile=candidate.signal_config,
                dataset_version=f"live:{candles[-1].open_time}",
                profile_id=candidate.id,
            )
            production_payload = _decision_payload(reference)
            candidate_payload = _decision_payload(challenger)
            reasons = [
                key
                for key in (
                    "accepted",
                    "rejection_stage",
                    "confluence_score",
                    "confluence_grade",
                    "divergences",
                )
                if production_payload[key] != candidate_payload[key]
            ]
            await self.repository.add_shadow(
                ShadowComparison(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=reference.decision_time,
                    production_profile_id=production.id,
                    candidate_profile_id=candidate.id,
                    production=production_payload,
                    candidate=candidate_payload,
                    divergence_reasons=reasons,
                )
            )
            written += 1
        return written


def _decision_payload(observation: SignalObservation) -> dict[str, object]:
    return {
        "accepted": observation.accepted,
        "rejection_stage": observation.rejection_stage,
        "rejection_reason": observation.rejection_reason,
        "confluence_score": observation.confluence_score,
        "confluence_grade": observation.confluence_grade,
        "factors": observation.confluence_factors,
        "availability": observation.availability,
        "divergences": observation.divergences,
        "algorithm_version": observation.algorithm_version,
        "profile_fingerprint": observation.profile_fingerprint,
    }
