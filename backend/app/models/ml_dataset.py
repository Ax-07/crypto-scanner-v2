"""Contrats versionnés des lignes du dataset causal de machine learning."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Final, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ML_DATASET_SCHEMA_VERSION: Final[Literal[1]] = 1
ML_FEATURE_SCHEMA_VERSION: Final[
    Literal["causal-features-v1"]
] = "causal-features-v1"
ML_LABEL_SCHEMA_VERSION: Final[
    Literal["direction-natr-h6-v1"]
] = "direction-natr-h6-v1"

MLFeatureValue: TypeAlias = bool | int | float | str | None


class MarketDirectionLabel(StrEnum):
    """Direction future du marché à l'horizon étudié."""

    DOWN = "down"
    NEUTRAL = "neutral"
    UP = "up"


class MLDatasetRow(BaseModel):
    """Une ligne causale associant une observation à son label futur.

    Les éléments de ``features`` doivent être connus au plus tard à
    ``decision_time``. Les champs futurs sont conservés hors de ``features``
    afin de limiter les risques de fuite de données pendant l'entraînement.
    """

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )

    dataset_schema_version: Literal[1] = ML_DATASET_SCHEMA_VERSION
    feature_schema_version: Literal["causal-features-v1"] = ML_FEATURE_SCHEMA_VERSION
    label_schema_version: Literal["direction-natr-h6-v1"] = ML_LABEL_SCHEMA_VERSION

    observation_id: int = Field(gt=0)
    job_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)

    decision_time: datetime
    source_open_time: datetime | None = None

    snapshot_status: Literal["confirmed"] = "confirmed"
    calculation_mode: Literal["canonical"] = "canonical"

    source_algorithm_version: str = Field(min_length=1)
    source_dataset_version: str = Field(min_length=1)
    profile_id: str = Field(default="inline", min_length=1)
    profile_fingerprint: str | None = None

    horizon: Literal[6] = 6
    entry_policy: Literal["signal_close", "next_open"]
    entry_time: datetime
    exit_time: datetime

    natr_percent: float = Field(gt=0)
    natr_multiplier: float = Field(default=1.0, gt=0, le=10)
    neutral_threshold_return: float = Field(gt=0)

    future_return: float
    label: MarketDirectionLabel

    features: dict[str, MLFeatureValue] = Field(min_length=1)

    @field_validator(
        "decision_time",
        "source_open_time",
        "entry_time",
        "exit_time",
    )
    @classmethod
    def normalize_datetimes(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Exige des dates timezone-aware et les normalise en UTC."""
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError("les dates du dataset doivent inclure un fuseau horaire")

        return value.astimezone(timezone.utc)

    @field_validator("features")
    @classmethod
    def validate_features(
        cls,
        value: dict[str, MLFeatureValue],
    ) -> dict[str, MLFeatureValue]:
        """Refuse les noms ambigus et les valeurs numériques non finies."""
        forbidden_exact_names = {
            "label",
            "future_return",
            "gross_return",
            "net_return",
            "mfe",
            "mae",
            "highest_price",
            "lowest_price",
            "exit_price",
            "exit_time",
        }
        forbidden_prefixes = (
            "target.",
            "outcome.",
            "future.",
        )

        for name, feature_value in value.items():
            if not name or name != name.strip():
                raise ValueError("chaque feature doit avoir un nom non vide et normalisé")

            if name in forbidden_exact_names or name.startswith(forbidden_prefixes):
                raise ValueError(f"feature future ou réservée interdite dans le dataset : {name}")

            if isinstance(feature_value, float) and not math.isfinite(feature_value):
                raise ValueError(f"la feature {name} contient une valeur non finie")

        return value

    @model_validator(mode="after")
    def validate_causal_row(self) -> "MLDatasetRow":
        """Valide la chronologie, le seuil NATR et la classe directionnelle."""
        if self.source_open_time is not None and self.source_open_time > self.decision_time:
            raise ValueError("source_open_time ne peut pas être postérieur à decision_time")

        if self.entry_time < self.decision_time:
            raise ValueError("entry_time ne peut pas être antérieur à decision_time")

        if self.exit_time <= self.entry_time:
            raise ValueError("exit_time doit être postérieur à entry_time")

        expected_threshold = self.natr_percent / 100 * self.natr_multiplier

        if not math.isclose(
            self.neutral_threshold_return,
            expected_threshold,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "neutral_threshold_return doit être égal à " "natr_percent / 100 * natr_multiplier"
            )

        if self.future_return > self.neutral_threshold_return:
            expected_label = MarketDirectionLabel.UP
        elif self.future_return < -self.neutral_threshold_return:
            expected_label = MarketDirectionLabel.DOWN
        else:
            expected_label = MarketDirectionLabel.NEUTRAL

        if self.label != expected_label:
            raise ValueError(
                "label incohérent avec future_return et le seuil NATR : "
                f"{self.label} != {expected_label}"
            )

        return self
