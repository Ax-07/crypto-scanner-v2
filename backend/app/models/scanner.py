"""Contrats Pydantic publics des jobs, progressions et résultats de scan."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.core.settings import ScanConfig
from app.domain.indicators import (
    Availability,
    BollingerPosition,
    ConfluenceGrade,
    MacdSignal,
    SignalDirection,
    StochasticSignal,
    TrendState,
)


class IndicatorSignalModel(BaseModel):
    """Miroir Pydantic additif du contrat ``IndicatorSignal`` (voir
    ``app.domain.indicators.types``), pour exposition publique typée dans
    ``ScanResult``/``SignalObservation`` sans dépendre du ``TypedDict``
    interne.
    """

    status: Availability
    direction: SignalDirection
    signal: str | None = None
    state: str | None = None
    strength: float = Field(ge=0.0, le=1.0)
    reason: str | None = None
    raw_value: float | None = None


class ScanStatus(StrEnum):
    """États successifs possibles d'un job de scan."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanProgress(BaseModel):
    """Compteurs de progression d'un scan en cours.

    Pour chaque symbole terminé, exactement un compteur parmi ``successful``,
    ``filtered`` et ``errors`` est incrémenté avec ``processed``.
    """

    processed: int = Field(default=0, description="Nombre de symboles dont l'analyse est terminée.")
    total: int = Field(default=0, description="Nombre total de symboles retenus pour le scan.")
    successful: int = 0
    filtered: int = 0
    errors: int = 0

    @property
    def percent(self) -> float:
        """Calcule la progression sur 100, arrondie à deux décimales."""
        return round((self.processed / self.total) * 100, 2) if self.total else 0.0


class ScanResult(BaseModel):
    """Résultat technique d'une paire ayant franchi tous les filtres actifs.

    Les champs liés à un indicateur désactivé ou non calculable restent à
    ``None``; les collections correspondantes restent vides.
    """

    symbol: str
    timeframe: str
    rsi: float | None = None
    last_close_price: float | None = None
    last_close_time: datetime | None = None
    trend_score: int | None = None
    trends: dict[str, bool | None] = Field(default_factory=dict)
    trend_states: dict[str, TrendState] = Field(default_factory=dict)
    trend_net_score: int | None = None
    moving_averages: dict[str, float] = Field(default_factory=dict)
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    macd_signal_type: MacdSignal | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_position: BollingerPosition | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
    stoch_signal: StochasticSignal | None = None
    confluence_score: float | None = None
    confluence_grade: ConfluenceGrade | None = None
    confluence_breakdown: dict[str, float] = Field(default_factory=dict)
    confluence_effective_weights: dict[str, float] = Field(default_factory=dict)
    confluence_details: dict[str, dict[str, Any]] = Field(default_factory=dict)
    indicator_availability: dict[str, Availability] = Field(default_factory=dict)
    indicator_signals: dict[str, IndicatorSignalModel] = Field(default_factory=dict)


class ScanJob(BaseModel):
    """État en mémoire d'un scan asynchrone et de ses résultats."""

    id: str = Field(description="Identifiant hexadécimal unique du job.")
    status: ScanStatus = ScanStatus.PENDING
    config: ScanConfig
    progress: ScanProgress = Field(default_factory=ScanProgress)
    results: list[ScanResult] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def public_payload(self, include_results: bool = False) -> dict[str, Any]:
        """Produit le payload REST/WebSocket stable exposé aux clients.

        Args:
            include_results: Ajoute la liste complète des résultats si vrai.

        Returns:
            Représentation JSON avec ``progress.percent`` et ``result_count``.
        """
        payload = self.model_dump(mode="json", exclude={"results"})
        payload["progress"]["percent"] = self.progress.percent
        payload["result_count"] = len(self.results)
        if include_results:
            payload["results"] = [item.model_dump(mode="json") for item in self.results]
        return payload
