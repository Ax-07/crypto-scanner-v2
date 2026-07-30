"""Contrats publics de validation historique des signaux."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

from app.core.settings import ScanConfig
from app.domain.indicators import Availability, ConfluenceGrade, TrendState
from app.domain.portfolio import PortfolioSimulationResult
from app.models.scanner import IndicatorSignalModel
from app.models.portfolio import (
    PortfolioSimulationConfigV1,
    PortfolioSimulationPublicResult,
)


class BacktestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class BacktestConfig(BaseModel):
    """Configuration reproductible; ``signal_config`` est le contrat de production."""

    symbols: list[str] = Field(min_length=1, max_length=500)
    start: datetime
    end: datetime
    signal_config: ScanConfig = Field(default_factory=ScanConfig)
    horizons: list[int] = Field(default_factory=lambda: [1, 3, 6, 12, 24])
    replay_mode: Literal["every_bar", "state_changes", "filtered_signals"] = "every_bar"
    entry_policy: Literal["signal_close", "next_open"] = "signal_close"
    gap_policy: Literal["reject_range", "skip_affected", "allow_with_warning"] = "reject_range"
    fee_bps: float = Field(default=0, ge=0, le=1_000)
    slippage_bps: float = Field(default=0, ge=0, le=1_000)
    snapshot_status: Literal["confirmed", "provisional"] = "confirmed"
    portfolio_simulation: PortfolioSimulationConfigV1 | None = Field(
        default=None,
        description=(
            "Simulation séquentielle optionnelle, distincte des rendements futurs "
            "indépendants. Son absence conserve le replay historique."
        ),
    )

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value if item.strip()]
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("symbols doit contenir des symboles uniques non vides")
        return normalized

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("les dates doivent inclure un fuseau horaire")
        return value.astimezone(timezone.utc)

    @field_validator("horizons")
    @classmethod
    def validate_horizons(cls, value: list[int]) -> list[int]:
        cleaned = sorted(set(value))
        if not cleaned or any(item < 1 or item > 10_000 for item in cleaned):
            raise ValueError("horizons doit contenir des nombres de bougies entre 1 et 10000")
        return cleaned

    @model_validator(mode="after")
    def validate_range(self) -> "BacktestConfig":
        if self.start >= self.end:
            raise ValueError("start doit précéder end")
        portfolio = self.portfolio_simulation
        if portfolio is not None:
            if len(self.symbols) != 1:
                raise ValueError("portfolio_simulation exige exactement un symbole")
            if self.replay_mode != "every_bar":
                raise ValueError("portfolio_simulation exige replay_mode='every_bar'")
            symbol = self.symbols[0]
            if "/" in symbol:
                symbol_quote = symbol.rsplit("/", 1)[1]
                if symbol_quote != portfolio.quote_asset:
                    raise ValueError(
                        "portfolio_simulation.quote_asset est incohérent avec le symbole"
                    )
        return self


class BacktestProgress(BaseModel):
    processed: int = 0
    total: int = 0
    observations: int = 0
    current_symbol: str | None = None
    phase: str = "queued"

    @property
    def percent(self) -> float:
        return round(self.processed / self.total * 100, 2) if self.total else 0.0


class SignalObservation(BaseModel):
    id: int | None = None
    job_id: str
    symbol: str
    timeframe: str
    decision_time: datetime
    snapshot_status: Literal["confirmed", "provisional"] = "confirmed"
    accepted: bool
    rejection_stage: str | None = None
    rejection_reason: str | None = None
    close: float
    rsi: float | None = None
    trend_score: int | None = None
    trend_states: dict[str, TrendState] = Field(default_factory=dict)
    macd_signal: str | None = None
    bollinger_position: str | None = None
    stochastic_signal: str | None = None
    confluence_score: float | None = None
    confluence_grade: ConfluenceGrade | None = None
    confluence_factors: dict[str, float | None] = Field(default_factory=dict)
    availability: dict[str, Availability] = Field(default_factory=dict)
    indicator_signals: dict[str, IndicatorSignalModel] = Field(default_factory=dict)
    filter_trace: list[dict[str, Any]] = Field(default_factory=list)
    algorithm_version: str = "signal-evaluation-v2"
    profile_id: str = "inline"
    profile_fingerprint: str | None = None
    dataset_version: str = "unknown"
    calculation_mode: Literal["canonical"] = "canonical"
    schema_version: int = 2
    created_at: datetime | None = None
    source_open_time: datetime | None = None
    source_ohlcv: dict[str, float] = Field(default_factory=dict)
    raw_values: dict[str, Any] = Field(default_factory=dict)
    classes: dict[str, str | None] = Field(default_factory=dict)
    trend_net_score: int | None = None
    confluence_breakdown: dict[str, float] = Field(default_factory=dict)
    configured_weights: dict[str, float] = Field(default_factory=dict)
    effective_weights: dict[str, float] = Field(default_factory=dict)
    signal_profile: dict[str, Any] = Field(default_factory=dict)
    divergences: list[dict[str, Any]] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def deterministic_creation_time(self) -> "SignalObservation":
        if self.created_at is None:
            self.created_at = self.decision_time
        return self


class ForwardOutcome(BaseModel):
    observation_id: int | None = None
    horizon: int
    entry_policy: Literal["signal_close", "next_open"]
    entry_time: datetime | None = None
    entry_price: float | None = None
    exit_time: datetime | None = None
    exit_price: float | None = None
    gross_return: float | None = None
    net_return: float | None = None
    mfe: float | None = None
    mae: float | None = None
    censored: bool = False
    censor_reason: str | None = None
    highest_price: float | None = None
    lowest_price: float | None = None
    available_bars: int = 0
    valid: bool = True


class BacktestSummary(BaseModel):
    observation_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    censored_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    horizons: dict[str, dict[str, Any]] = Field(default_factory=dict)
    segments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    filter_funnel: list[dict[str, Any]] = Field(default_factory=list)
    provisional_supported: bool = False
    trade_simulation_included: bool = False
    portfolio_simulation: PortfolioSimulationPublicResult | None = None

    def public_payload(self) -> dict[str, Any]:
        """Omet le nouveau bloc lorsqu'il est absent pour préserver le JSON historique."""
        exclude = {"portfolio_simulation"} if self.portfolio_simulation is None else None
        return self.model_dump(mode="json", exclude=exclude)


class BacktestJob(BaseModel):
    id: str
    status: BacktestStatus = BacktestStatus.PENDING
    config: BacktestConfig
    progress: BacktestProgress = Field(default_factory=BacktestProgress)
    summary: BacktestSummary | None = None
    correlations: dict[str, Any] | None = None
    ablations: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    dataset_version: str = "unknown"
    algorithm_version: str = "signal-evaluation-v2"
    checkpoint: dict[str, Any] | None = None
    config_fingerprint: str | None = None
    _portfolio_result: PortfolioSimulationResult | None = PrivateAttr(default=None)

    @property
    def portfolio_result(self) -> PortfolioSimulationResult | None:
        """Retourne le résultat détaillé uniquement conservé en mémoire."""
        return self._portfolio_result

    def set_portfolio_result(self, result: PortfolioSimulationResult | None) -> None:
        """Remplace atomiquement le détail interne non sérialisé."""
        self._portfolio_result = result

    def public_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        if self.config.portfolio_simulation is None:
            payload["config"].pop("portfolio_simulation", None)
            payload.pop("config_fingerprint", None)
        if self.summary is not None:
            payload["summary"] = self.summary.public_payload()
        payload["progress"]["percent"] = self.progress.percent
        return payload
