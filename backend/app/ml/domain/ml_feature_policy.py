"""Politiques déterministes de sélection des features ML."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

from app.ml.models.ml_dataset import MLDatasetRow


class MLFeaturePolicyError(ValueError):
    """Signale une politique de features inconnue."""


class MLFeaturePolicy(StrEnum):
    """Politiques disponibles avant le prétraitement."""

    ALL = "all"
    WITHOUT_ABSOLUTE = "without_absolute"
    WITHOUT_DUPLICATES = "without_duplicates"
    NORMALIZED_DEDUPLICATED = "normalized_deduplicated"


ABSOLUTE_FEATURE_NAMES: frozenset[str] = frozenset(
    {
        "candle.open",
        "candle.high",
        "candle.low",
        "candle.close",
        "candle.volume",
        "price.close",
        "indicator.atr.component.atr.value",
        "indicator.atr.component.true_range.value",
        ("indicator.bollinger.component." "band_width.value"),
        ("indicator.bollinger.component." "lower_band.value"),
        ("indicator.bollinger.component." "middle_band.value"),
        ("indicator.bollinger.component." "upper_band.value"),
        "quality.quote_volume_median",
    }
)


DUPLICATE_FEATURE_NAMES: frozenset[str] = frozenset(
    {
        "indicator.atr.component.natr.value",
        ("indicator.atr.component." "natr.normalized_value"),
        "indicator.atr.raw_value",
        ("indicator.bollinger.component." "band_position.normalized_value"),
        ("indicator.bollinger.component." "band_width_percent.normalized_value"),
        "price.close",
    }
)


@dataclass(frozen=True, slots=True)
class MLFeaturePolicyApplication:
    """Résultat d'une politique appliquée à un dataset."""

    policy: MLFeaturePolicy
    rows: tuple[MLDatasetRow, ...]

    source_feature_names: tuple[str, ...]
    excluded_feature_names: tuple[str, ...]
    excluded_present_feature_names: tuple[str, ...]
    retained_feature_names: tuple[str, ...]

    @property
    def source_feature_count(self) -> int:
        """Retourne le nombre de features avant filtrage."""
        return len(self.source_feature_names)

    @property
    def excluded_present_feature_count(self) -> int:
        """Retourne le nombre de features réellement retirées."""
        return len(self.excluded_present_feature_names)

    @property
    def retained_feature_count(self) -> int:
        """Retourne le nombre de features après filtrage."""
        return len(self.retained_feature_names)


def normalize_feature_policy(
    policy: MLFeaturePolicy | str,
) -> MLFeaturePolicy:
    """Normalise une politique reçue sous forme d'enum ou de texte."""
    if isinstance(
        policy,
        MLFeaturePolicy,
    ):
        return policy

    try:
        return MLFeaturePolicy(policy)
    except ValueError as exc:
        raise MLFeaturePolicyError(f"politique de features inconnue : {policy}") from exc


def feature_policy_exclusions(
    policy: MLFeaturePolicy | str,
) -> frozenset[str]:
    """Retourne les features exclues par une politique."""
    normalized_policy = normalize_feature_policy(policy)

    if normalized_policy == MLFeaturePolicy.ALL:
        return frozenset()

    if normalized_policy == MLFeaturePolicy.WITHOUT_ABSOLUTE:
        return ABSOLUTE_FEATURE_NAMES

    if normalized_policy == MLFeaturePolicy.WITHOUT_DUPLICATES:
        return DUPLICATE_FEATURE_NAMES

    if normalized_policy == MLFeaturePolicy.NORMALIZED_DEDUPLICATED:
        return ABSOLUTE_FEATURE_NAMES | DUPLICATE_FEATURE_NAMES

    raise MLFeaturePolicyError(
        "politique de features non prise en charge : " f"{normalized_policy.value}"
    )


def apply_ml_feature_policy(
    rows: Sequence[MLDatasetRow],
    *,
    policy: MLFeaturePolicy | str,
) -> MLFeaturePolicyApplication:
    """Retire les features interdites sans modifier les lignes sources."""
    normalized_policy = normalize_feature_policy(policy)
    exclusions = feature_policy_exclusions(normalized_policy)

    source_feature_names = frozenset(feature_name for row in rows for feature_name in row.features)

    excluded_present_feature_names = tuple(sorted(source_feature_names & exclusions))
    retained_feature_names = tuple(sorted(source_feature_names - exclusions))

    filtered_rows = tuple(
        row.model_copy(
            update={
                "features": {
                    feature_name: value
                    for feature_name, value in row.features.items()
                    if feature_name not in exclusions
                }
            }
        )
        for row in rows
    )

    return MLFeaturePolicyApplication(
        policy=normalized_policy,
        rows=filtered_rows,
        source_feature_names=tuple(sorted(source_feature_names)),
        excluded_feature_names=tuple(sorted(exclusions)),
        excluded_present_feature_names=(excluded_present_feature_names),
        retained_feature_names=(retained_feature_names),
    )
