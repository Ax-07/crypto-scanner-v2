"""Façade canonique pure pour l'évaluation d'un snapshot de signal.

Tous les consommateurs historiques et shadow doivent passer par cette façade.
Elle garde le contrat d'entrée explicite et délègue les primitives à leur source
de vérité existante.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.core.settings import ScanConfig
from app.domain.candles import Candle
from app.models.backtest import SignalObservation


def evaluate_signal_snapshot(
    *,
    job_id: str,
    symbol: str,
    decision_time_ms: int,
    primary: Sequence[Candle],
    trend_candles: Mapping[str, Sequence[Candle]],
    profile: ScanConfig,
    snapshot_status: str = "confirmed",
    dataset_version: str = "unknown",
    profile_id: str = "inline",
) -> SignalObservation:
    """Évalue causalement un snapshot sans accès aux outcomes futurs."""
    from app.domain.backtesting import evaluate_information_set

    return evaluate_information_set(
        job_id=job_id,
        symbol=symbol,
        decision_time_ms=decision_time_ms,
        primary=primary,
        trend_candles=trend_candles,
        config=profile,
        snapshot_status=snapshot_status,
        dataset_version=dataset_version,
        profile_id=profile_id,
    )


__all__ = ["evaluate_signal_snapshot"]
