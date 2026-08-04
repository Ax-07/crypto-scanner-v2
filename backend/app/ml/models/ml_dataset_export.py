"""Contrats versionnés de l'export reproductible d'un dataset ML."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.ml.models.ml_dataset import (
    ML_DATASET_SCHEMA_VERSION,
    ML_FEATURE_SCHEMA_VERSION,
    ML_LABEL_SCHEMA_VERSION,
)

ML_EXPORT_MANIFEST_SCHEMA_VERSION: Final[Literal[1]] = 1
ML_EXPORT_FORMAT: Final[Literal["jsonl"]] = "jsonl"


class MLDatasetExportStats(BaseModel):
    """Compteurs associés à la construction du dataset exporté."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )

    source_rows: int = Field(ge=0)
    processed_rows: int = Field(ge=0)
    generated_rows: int = Field(ge=0)
    skipped_rows: int = Field(ge=0)

    censored_outcomes: int = Field(ge=0)
    invalid_outcomes: int = Field(ge=0)
    missing_natr: int = Field(ge=0)
    contract_rejections: int = Field(ge=0)

    batch_count: int = Field(ge=0)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)

    @field_validator("rejection_reasons")
    @classmethod
    def validate_rejection_reasons(
        cls,
        value: dict[str, int],
    ) -> dict[str, int]:
        """Refuse les raisons vides et les compteurs négatifs."""
        normalized: dict[str, int] = {}

        for reason, count in value.items():
            cleaned_reason = reason.strip()

            if not cleaned_reason:
                raise ValueError("une raison de rejet ne peut pas être vide")

            if count < 1:
                raise ValueError("un compteur de raison doit être supérieur à zéro")

            normalized[cleaned_reason] = count

        return dict(sorted(normalized.items()))

    @model_validator(mode="after")
    def validate_counters(
        self,
    ) -> "MLDatasetExportStats":
        """Valide les invariants de comptabilisation."""
        categorized_skips = (
            self.censored_outcomes
            + self.invalid_outcomes
            + self.missing_natr
            + self.contract_rejections
        )

        if self.skipped_rows != categorized_skips:
            raise ValueError("skipped_rows doit être égal à la somme " "des catégories de rejet")

        if self.generated_rows + self.skipped_rows != self.processed_rows:
            raise ValueError("generated_rows + skipped_rows doit être égal " "à processed_rows")

        if self.processed_rows != self.source_rows:
            raise ValueError("processed_rows doit être égal à source_rows")

        if sum(self.rejection_reasons.values()) != self.contract_rejections:
            raise ValueError(
                "la somme de rejection_reasons doit être égale " "à contract_rejections"
            )

        return self


class MLDatasetExportManifest(BaseModel):
    """Manifeste déterministe décrivant un export JSONL."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )

    manifest_schema_version: Literal[1] = ML_EXPORT_MANIFEST_SCHEMA_VERSION

    export_format: Literal["jsonl"] = ML_EXPORT_FORMAT

    dataset_schema_version: Literal[1] = ML_DATASET_SCHEMA_VERSION

    feature_schema_version: Literal["causal-features-v1"] = ML_FEATURE_SCHEMA_VERSION

    label_schema_version: Literal["direction-natr-h6-v1"] = ML_LABEL_SCHEMA_VERSION

    source_job_id: str = Field(min_length=1)
    horizon: Literal[6]
    natr_multiplier: float = Field(gt=0, le=10)

    data_file: str = Field(min_length=1)
    data_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    row_count: int = Field(ge=0)
    first_decision_time: datetime | None = None
    last_decision_time: datetime | None = None

    feature_names: list[str] = Field(default_factory=list)
    source_algorithm_versions: list[str] = Field(default_factory=list)
    source_dataset_versions: list[str] = Field(default_factory=list)
    profile_ids: list[str] = Field(default_factory=list)
    profile_fingerprints: list[str] = Field(default_factory=list)

    stats: MLDatasetExportStats

    @field_validator("source_job_id", "data_file")
    @classmethod
    def normalize_required_string(
        cls,
        value: str,
    ) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("la chaîne ne peut pas être vide")

        return cleaned

    @field_validator(
        "feature_names",
        "source_algorithm_versions",
        "source_dataset_versions",
        "profile_ids",
        "profile_fingerprints",
    )
    @classmethod
    def normalize_sorted_unique_strings(
        cls,
        value: list[str],
    ) -> list[str]:
        """Normalise les collections pour stabiliser le manifeste."""
        normalized = [item.strip() for item in value if item.strip()]

        return sorted(set(normalized))

    @field_validator(
        "first_decision_time",
        "last_decision_time",
    )
    @classmethod
    def normalize_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError("les dates du manifeste doivent inclure " "un fuseau horaire")

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_manifest(
        self,
    ) -> "MLDatasetExportManifest":
        """Valide la cohérence entre les lignes et le manifeste."""
        if self.row_count != self.stats.generated_rows:
            raise ValueError("row_count doit être égal à stats.generated_rows")

        if self.row_count == 0:
            if self.first_decision_time is not None or self.last_decision_time is not None:
                raise ValueError("un dataset vide ne doit pas déclarer " "de bornes temporelles")
        else:
            if self.first_decision_time is None or self.last_decision_time is None:
                raise ValueError("un dataset non vide doit déclarer " "ses bornes temporelles")

            if self.first_decision_time > self.last_decision_time:
                raise ValueError(
                    "first_decision_time ne peut pas être " "postérieur à last_decision_time"
                )

        return self
