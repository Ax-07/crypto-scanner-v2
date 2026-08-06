"""Contrat versionné du rapport d'audit d'un dataset ML v2."""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ML_DATASET_AUDIT_SCHEMA_VERSION: Final[Literal["ml-dataset-audit-v1"]] = "ml-dataset-audit-v1"
ML_DATASET_AUDITOR_VERSION: Final = "ml-dataset-auditor-v1"

AuditConclusion = Literal[
    "accepted_for_experiment_design",
    "accepted_with_reservations",
    "rejected",
]


class MLDatasetAuditReport(BaseModel):
    """Rapport canonique sans horodatage, chemin absolu ni état machine."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    audit_schema_version: Literal["ml-dataset-audit-v1"] = ML_DATASET_AUDIT_SCHEMA_VERSION
    auditor_version: str = ML_DATASET_AUDITOR_VERSION
    dataset_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dataset: dict[str, Any]
    source: dict[str, Any]
    funnel: dict[str, Any]
    structure: dict[str, Any]
    temporal: dict[str, Any]
    labels: dict[str, Any]
    features: dict[str, Any]
    correlations: dict[str, Any]
    outliers: dict[str, Any]
    regimes: dict[str, Any]
    stability: dict[str, Any]
    causal_audit: dict[str, Any]
    leak_audit: dict[str, Any]
    blocking_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conclusion: AuditConclusion

    @model_validator(mode="after")
    def validate_conclusion(self) -> "MLDatasetAuditReport":
        expected: AuditConclusion
        if self.blocking_failures:
            expected = "rejected"
        elif self.warnings:
            expected = "accepted_with_reservations"
        else:
            expected = "accepted_for_experiment_design"
        if self.conclusion != expected:
            raise ValueError("la conclusion ne correspond pas aux contrôles d'audit")
        return self
