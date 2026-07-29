"""Contrats versionnés de recherche, promotion et comparaison shadow."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.settings import ScanConfig
from app.models.backtest import BacktestStatus

SIGNAL_ALGORITHM_VERSION = "baseline-v1"
RANKING_VERSION = "robust-net-median-v1"
MAX_EXPERIMENT_CANDIDATES = 128


class ProfileStatus(StrEnum):
    DRAFT = "draft"
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    PRODUCTION = "production"
    RETIRED = "retired"


class SignalProfileVersion(BaseModel):
    """Profil publié immutable; toute évolution reçoit un nouvel identifiant."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    version: str
    algorithm_version: str = SIGNAL_ALGORITHM_VERSION
    parent_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    origin: str = "phase-4"
    description: str
    signal_config: ScanConfig
    experiment_id: str | None = None
    dataset_version: str
    code_version: str
    snapshot_status: Literal["confirmed", "provisional"] = "confirmed"
    status: ProfileStatus = ProfileStatus.DRAFT
    content_hash: str = ""

    @model_validator(mode="after")
    def set_content_hash(self) -> "SignalProfileVersion":
        content = self.model_dump(mode="json", exclude={"status", "content_hash"})
        fingerprint = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        object.__setattr__(self, "content_hash", f"sha256:{fingerprint}")
        return self


class SplitConfig(BaseModel):
    train_ratio: float = Field(default=0.6, gt=0, lt=1)
    validation_ratio: float = Field(default=0.2, gt=0, lt=1)
    test_ratio: float = Field(default=0.2, gt=0, lt=1)
    embargo_bars: int = Field(default=24, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_total(self) -> "SplitConfig":
        if abs(self.train_ratio + self.validation_ratio + self.test_ratio - 1) > 1e-9:
            raise ValueError("les ratios train/validation/test doivent totaliser 1")
        return self


class WalkForwardConfig(BaseModel):
    enabled: bool = True
    train_bars: int = Field(default=240, ge=10)
    validation_bars: int = Field(default=60, ge=5)
    oos_bars: int = Field(default=10, ge=5)
    step_bars: int = Field(default=60, ge=1)
    max_folds: int = Field(default=12, ge=1, le=100)


class CandidateSpec(BaseModel):
    id: str
    family: Literal[
        "baseline",
        "trend",
        "redundancy",
        "weights",
        "thresholds",
        "bollinger",
        "divergence",
        "liquidity",
        "regime",
        "timeframe",
    ] = "baseline"
    description: str = ""
    weights: dict[str, int] = Field(default_factory=dict)
    rsi_threshold: float | None = Field(default=None, ge=0, le=100)
    min_confluence_score: float | None = Field(default=None, ge=0, le=100)
    excluded_factors: set[str] = Field(default_factory=set)
    group_scoring: bool = False
    mean_reversion_cap: float | None = Field(default=None, ge=0, le=100)
    trend_policy: Literal[
        "baseline",
        "strict_consensus",
        "single_family_fallback",
        "price_alignment",
        "mtf_majority",
        "mtf_weighted",
    ] = "baseline"
    min_quote_volume: float | None = Field(default=None, ge=0)
    bollinger_policy: Literal["baseline", "below_mid", "lower_band"] = "baseline"
    stochastic_policy: Literal["baseline", "bullish", "oversold"] = "baseline"
    macd_policy: Literal["baseline", "bullish"] = "baseline"
    divergence_required: bool = False
    divergence_kinds: set[Literal["regular", "hidden"]] = Field(default_factory=set)
    divergence_directions: set[Literal["bullish", "bearish"]] = Field(default_factory=set)
    min_data_quality: float = Field(default=0.0, ge=0, le=1)
    allowed_timeframes: set[str] = Field(default_factory=set)
    regime: Literal["all", "trend", "range"] = "all"

    @field_validator("weights")
    @classmethod
    def bounded_weights(cls, value: dict[str, int]) -> dict[str, int]:
        if len(value) > 5 or any(
            weight < 0 or weight > 40 or weight % 5 for weight in value.values()
        ):
            raise ValueError("poids: au plus cinq facteurs, valeurs 0..40 par pas de 5")
        if value and sum(value.values()) <= 0:
            raise ValueError("la somme des poids doit être positive")
        return value


class ExperimentConfig(BaseModel):
    source_backtest_id: str
    baseline_profile_id: str = "baseline-v1"
    candidates: list[CandidateSpec] = Field(min_length=1, max_length=MAX_EXPERIMENT_CANDIDATES)
    split: SplitConfig = Field(default_factory=SplitConfig)
    walk_forward: WalkForwardConfig = Field(default_factory=WalkForwardConfig)
    selection_horizon: int = Field(default=24, ge=1, le=10_000)
    minimum_global: int = Field(default=30, ge=1)
    minimum_per_fold: int = Field(default=5, ge=1)
    minimum_per_timeframe: int = Field(default=5, ge=1)
    minimum_symbols: int = Field(default=2, ge=1)
    minimum_calendar_periods: int = Field(default=2, ge=1)
    seed: int = 42
    bootstrap_samples: int = Field(default=500, ge=100, le=10_000)
    bootstrap_block_size: int = Field(default=8, ge=1, le=1_000)
    multiplicity_alpha: float = Field(default=0.10, gt=0, lt=1)
    cost_scenarios_bps: list[float] = Field(default_factory=lambda: [0.0, 5.0, 10.0, 20.0])
    ranking_version: Literal["robust-net-median-v1"] = "robust-net-median-v1"
    objective_split: Literal["train_validation"] = "train_validation"
    linked_experiment_ids: list[str] = Field(default_factory=list)
    promotion_criteria: dict[str, float] = Field(
        default_factory=lambda: {
            "max_validation_degradation": 0.005,
            "max_symbol_concentration": 0.70,
            "max_local_sensitivity": 0.01,
            "max_oos_degradation": 0.01,
        }
    )

    @model_validator(mode="after")
    def validate_candidates(self) -> "ExperimentConfig":
        ids = [item.id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("les identifiants candidats doivent être uniques")
        if not any(item.family == "baseline" for item in self.candidates):
            raise ValueError("la baseline doit faire partie de chaque expérience")
        if self.split.embargo_bars < self.selection_horizon:
            raise ValueError("l'embargo doit être au moins égal à l'horizon sélectionné")
        return self


class EvaluationWindow(BaseModel):
    name: str
    start: datetime
    end: datetime
    observation_count: int


class CandidateResult(BaseModel):
    candidate_id: str
    family: str
    rank: int | None = None
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    walk_forward: list[dict[str, Any]] = Field(default_factory=list)
    sensitivity: dict[str, Any] = Field(default_factory=dict)
    oos_metrics: dict[str, Any] = Field(default_factory=dict)
    final_test_metrics: dict[str, Any] = Field(default_factory=dict)
    adjusted_p_value: float | None = None
    selection_reason: str | None = None
    robust_score: float | None = None
    selected: bool = False


class ExperimentManifest(BaseModel):
    id: str
    status: BacktestStatus = BacktestStatus.PENDING
    config: ExperimentConfig
    dataset_version: str
    code_version: str
    algorithm_version: str = SIGNAL_ALGORITHM_VERSION
    candidate_count: int
    total_trials: int
    search_space: dict[str, Any]
    splits: list[EvaluationWindow] = Field(default_factory=list)
    results: list[CandidateResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class PromotionDecision(BaseModel):
    profile_id: str
    experiment_id: str
    approved: bool
    criteria: dict[str, bool]
    comment: str = Field(min_length=3, max_length=2_000)
    previous_profile_id: str | None = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShadowComparison(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    production_profile_id: str
    candidate_profile_id: str
    production: dict[str, Any]
    candidate: dict[str, Any]
    divergence_reasons: list[str]
    snapshot_status: Literal["confirmed"] = "confirmed"
    future_outcome: dict[str, Any] | None = None
