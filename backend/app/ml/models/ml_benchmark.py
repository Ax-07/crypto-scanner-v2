"""Contrats versionnés des benchmarks ML consommant un test final."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ML_BENCHMARK_SCHEMA_VERSION: Literal["ml-benchmark-v1"] = "ml-benchmark-v1"

MLBenchmarkStatus = Literal[
    "accepted",
    "rejected",
]

MLBenchmarkFeaturePolicy = Literal[
    "all",
    "without_absolute",
    "without_duplicates",
    "normalized_deduplicated",
]


def _normalize_non_empty_string(
    value: object,
    *,
    field_name: str,
) -> str:
    """Normalise une chaîne obligatoire."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} doit être une chaîne")

    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{field_name} ne peut pas être vide")

    return normalized


def _normalize_string_collection(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Normalise une collection textuelle triée et unique."""
    if not isinstance(
        value,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        raise ValueError(f"{field_name} doit être une collection")

    normalized: set[str] = set()

    for item in value:
        normalized.add(
            _normalize_non_empty_string(
                item,
                field_name=field_name,
            )
        )

    return tuple(sorted(normalized))


def _normalize_utc_datetime(
    value: datetime,
    *,
    field_name: str,
) -> datetime:
    """Normalise un instant timezone-aware en UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} doit inclure un fuseau horaire")

    return value.astimezone(timezone.utc)


class MLBenchmarkLabelCounts(BaseModel):
    """Effectifs directionnels dans l'ordre métier."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    down: int = Field(
        ge=0,
    )
    neutral: int = Field(
        ge=0,
    )
    up: int = Field(
        ge=0,
    )

    @property
    def total(self) -> int:
        """Retourne l'effectif total."""
        return self.down + self.neutral + self.up


class MLBenchmarkMetricSnapshot(BaseModel):
    """Résumé stable des métriques d'une partition."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    row_count: int = Field(
        gt=0,
    )

    accuracy: float = Field(
        ge=0.0,
        le=1.0,
    )
    balanced_accuracy: float = Field(
        ge=0.0,
        le=1.0,
    )
    macro_f1: float = Field(
        ge=0.0,
        le=1.0,
    )
    weighted_f1: float = Field(
        ge=0.0,
        le=1.0,
    )

    predicted_label_counts: MLBenchmarkLabelCounts

    @model_validator(mode="after")
    def validate_counts(
        self,
    ) -> Self:
        """Vérifie la cohérence des prédictions."""
        if self.predicted_label_counts.total != self.row_count:
            raise ValueError("predicted_label_counts doit totaliser row_count")

        return self


class MLBenchmarkSelectionSnapshot(BaseModel):
    """Configuration choisie avant l'ouverture du test."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    selection_method: Literal["expanding_walk_forward"] = "expanding_walk_forward"

    policy: MLBenchmarkFeaturePolicy

    c_value: float = Field(
        gt=0.0,
    )

    fold_count: int = Field(
        gt=0,
    )
    validation_window: int = Field(
        gt=0,
    )
    minimum_train_window: int = Field(
        gt=0,
    )
    candidate_count: int = Field(
        gt=0,
    )
    total_validation_row_count: int = Field(
        gt=0,
    )

    output_feature_count_minimum: int = Field(
        gt=0,
    )
    output_feature_count_maximum: int = Field(
        gt=0,
    )

    mean_train_macro_f1: float = Field(
        ge=0.0,
        le=1.0,
    )
    mean_validation_macro_f1: float = Field(
        ge=0.0,
        le=1.0,
    )
    standard_deviation_validation_macro_f1: float = Field(
        ge=0.0,
        le=1.0,
    )
    minimum_validation_macro_f1: float = Field(
        ge=0.0,
        le=1.0,
    )
    pooled_validation_macro_f1: float = Field(
        ge=0.0,
        le=1.0,
    )
    mean_validation_balanced_accuracy: float = Field(
        ge=0.0,
        le=1.0,
    )

    mean_generalization_gap: float

    pooled_predicted_label_counts: MLBenchmarkLabelCounts

    @field_validator(
        "c_value",
        "mean_generalization_gap",
    )
    @classmethod
    def validate_finite_values(
        cls,
        value: float,
    ) -> float:
        """Refuse les flottants non finis."""
        if not math.isfinite(value):
            raise ValueError("la valeur doit être finie")

        return value

    @model_validator(mode="after")
    def validate_selection(
        self,
    ) -> Self:
        """Vérifie les dimensions agrégées."""
        if self.output_feature_count_minimum > self.output_feature_count_maximum:
            raise ValueError("output_feature_count_minimum " "ne peut pas dépasser le maximum")

        if self.pooled_predicted_label_counts.total != self.total_validation_row_count:
            raise ValueError(
                "les prédictions walk-forward doivent " "totaliser total_validation_row_count"
            )

        return self


class MLBenchmarkFeatureSnapshot(BaseModel):
    """Traçabilité de la sélection et du prétraitement."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    exported_feature_count: int = Field(
        gt=0,
    )

    excluded_present_feature_names: tuple[
        str,
        ...,
    ]

    preprocessing_input_feature_count: int = Field(
        gt=0,
    )

    dropped_constant_feature_names: tuple[
        str,
        ...,
    ]

    active_feature_count: int = Field(
        gt=0,
    )
    output_feature_count: int = Field(
        gt=0,
    )

    @field_validator(
        "excluded_present_feature_names",
        "dropped_constant_feature_names",
        mode="before",
    )
    @classmethod
    def normalize_feature_names(
        cls,
        value: object,
    ) -> tuple[str, ...]:
        """Normalise les listes de features."""
        return _normalize_string_collection(
            value,
            field_name="feature_names",
        )

    @model_validator(mode="after")
    def validate_feature_counts(
        self,
    ) -> Self:
        """Vérifie les étapes successives du filtrage."""
        if (
            self.preprocessing_input_feature_count + len(self.excluded_present_feature_names)
            != self.exported_feature_count
        ):
            raise ValueError(
                "les features exclues et les features "
                "de prétraitement doivent reconstituer "
                "exported_feature_count"
            )

        if (
            self.active_feature_count + len(self.dropped_constant_feature_names)
            != self.preprocessing_input_feature_count
        ):
            raise ValueError(
                "les features actives et constantes "
                "doivent reconstituer "
                "preprocessing_input_feature_count"
            )

        if self.output_feature_count < self.active_feature_count:
            raise ValueError(
                "output_feature_count ne peut pas être " "inférieur à active_feature_count"
            )

        return self


class MLBenchmarkReport(BaseModel):
    """Rapport immuable d'un test final consommé."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    benchmark_schema_version: Literal["ml-benchmark-v1"] = ML_BENCHMARK_SCHEMA_VERSION

    benchmark_name: str
    created_at: datetime

    status: MLBenchmarkStatus
    decision_reasons: tuple[
        str,
        ...,
    ]

    source_manifest_file: str
    source_data_file: str

    source_data_sha256: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    source_job_id: str

    manifest_schema_version: int = Field(
        gt=0,
    )
    dataset_schema_version: int = Field(
        gt=0,
    )

    feature_schema_version: str
    label_schema_version: str

    horizon: Literal[6]
    natr_multiplier: float = Field(
        gt=0.0,
    )

    dataset_row_count: int = Field(
        gt=0,
    )
    first_decision_time: datetime
    last_decision_time: datetime

    evaluation_start: datetime

    test_consumed: Literal[True] = True

    development_row_count: int = Field(
        gt=0,
    )
    excluded_target_overlap_count: int = Field(
        ge=0,
    )
    test_row_count: int = Field(
        gt=0,
    )

    selection: MLBenchmarkSelectionSnapshot
    features: MLBenchmarkFeatureSnapshot

    dummy_test: MLBenchmarkMetricSnapshot
    selected_model_development: MLBenchmarkMetricSnapshot
    selected_model_test: MLBenchmarkMetricSnapshot

    @field_validator(
        "benchmark_name",
        "source_job_id",
        "feature_schema_version",
        "label_schema_version",
        mode="before",
    )
    @classmethod
    def normalize_required_strings(
        cls,
        value: object,
        info: object,
    ) -> str:
        """Normalise les chaînes obligatoires."""
        field_name = getattr(
            info,
            "field_name",
            "value",
        )

        return _normalize_non_empty_string(
            value,
            field_name=field_name,
        )

    @field_validator(
        "source_manifest_file",
        "source_data_file",
        mode="before",
    )
    @classmethod
    def validate_simple_file_name(
        cls,
        value: object,
        info: object,
    ) -> str:
        """Interdit les chemins et traversées de dossiers."""
        field_name = getattr(
            info,
            "field_name",
            "file_name",
        )
        normalized = _normalize_non_empty_string(
            value,
            field_name=field_name,
        )

        path = Path(normalized)

        if (
            normalized
            in {
                ".",
                "..",
            }
            or path.is_absolute()
            or path.name != normalized
            or "/" in normalized
            or "\\" in normalized
        ):
            raise ValueError(f"{field_name} doit être " "un nom de fichier simple")

        return normalized

    @field_validator(
        "decision_reasons",
        mode="before",
    )
    @classmethod
    def normalize_decision_reasons(
        cls,
        value: object,
    ) -> tuple[str, ...]:
        """Normalise les raisons de décision."""
        return _normalize_string_collection(
            value,
            field_name="decision_reasons",
        )

    @field_validator(
        "created_at",
        "first_decision_time",
        "last_decision_time",
        "evaluation_start",
    )
    @classmethod
    def normalize_datetimes(
        cls,
        value: datetime,
        info: object,
    ) -> datetime:
        """Normalise tous les instants en UTC."""
        field_name = getattr(
            info,
            "field_name",
            "datetime",
        )

        return _normalize_utc_datetime(
            value,
            field_name=field_name,
        )

    @field_validator(
        "natr_multiplier",
    )
    @classmethod
    def validate_finite_multiplier(
        cls,
        value: float,
    ) -> float:
        """Refuse un multiplicateur non fini."""
        if not math.isfinite(value):
            raise ValueError("natr_multiplier doit être fini")

        return value

    @model_validator(mode="after")
    def validate_report(
        self,
    ) -> Self:
        """Vérifie la cohérence globale du benchmark."""
        if self.first_decision_time > self.last_decision_time:
            raise ValueError("first_decision_time ne peut pas " "suivre last_decision_time")

        if not (self.first_decision_time <= self.evaluation_start <= self.last_decision_time):
            raise ValueError("evaluation_start doit appartenir " "à la période du dataset")

        partitioned_row_count = (
            self.development_row_count + self.excluded_target_overlap_count + self.test_row_count
        )

        if partitioned_row_count != self.dataset_row_count:
            raise ValueError(
                "développement, purge et test doivent " "reconstituer dataset_row_count"
            )

        if self.dummy_test.row_count != self.test_row_count:
            raise ValueError("dummy_test.row_count doit correspondre " "à test_row_count")

        if self.selected_model_test.row_count != self.test_row_count:
            raise ValueError("selected_model_test.row_count doit " "correspondre à test_row_count")

        if self.selected_model_development.row_count != self.development_row_count:
            raise ValueError(
                "selected_model_development.row_count "
                "doit correspondre à "
                "development_row_count"
            )

        if self.status == "rejected" and not self.decision_reasons:
            raise ValueError("un benchmark rejeté doit fournir " "au moins une raison")

        return self
