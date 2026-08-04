"""Prétraitement déterministe des features ML."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Sequence, TypeGuard

import numpy as np
from numpy.typing import NDArray
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    OneHotEncoder,
    StandardScaler,
)

from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)

FeatureKind = Literal[
    "numeric",
    "boolean",
    "categorical",
]

MISSING_CATEGORY = "__missing__"

LABEL_ORDER = (
    MarketDirectionLabel.DOWN,
    MarketDirectionLabel.NEUTRAL,
    MarketDirectionLabel.UP,
)

LABEL_TO_INDEX = {label: index for index, label in enumerate(LABEL_ORDER)}


class MLPreprocessingError(ValueError):
    """Signale une feature invalide ou un prétraitement impossible."""


@dataclass(frozen=True, slots=True)
class MLFeatureSchema:
    """Contrat des features appris sur la partition d'entraînement."""

    input_feature_names: tuple[str, ...]
    active_feature_names: tuple[str, ...]
    dropped_constant_feature_names: tuple[str, ...]

    numeric_feature_names: tuple[str, ...]
    zero_fill_numeric_feature_names: tuple[str, ...]
    boolean_feature_names: tuple[str, ...]
    categorical_feature_names: tuple[str, ...]

    output_feature_names: tuple[str, ...]

    @property
    def input_feature_count(self) -> int:
        """Retourne le nombre de features sources observées."""
        return len(self.input_feature_names)

    @property
    def active_feature_count(self) -> int:
        """Retourne le nombre de features avant encodage."""
        return len(self.active_feature_names)

    @property
    def output_feature_count(self) -> int:
        """Retourne le nombre de colonnes après encodage."""
        return len(self.output_feature_names)


def _uses_zero_for_absence(
    feature_name: str,
) -> bool:
    """Indique qu'une absence signifie zéro occurrence."""
    return feature_name.startswith(
        (
            "event.",
            "divergence.",
        )
    )


def _is_numeric_value(
    value: object,
) -> TypeGuard[int | float]:
    """Détecte les nombres sans accepter les booléens."""
    return (
        isinstance(
            value,
            (
                int,
                float,
            ),
        )
        and not isinstance(value, bool)
    )


def _validated_numeric_value(
    feature_name: str,
    value: object,
) -> float:
    """Convertit une feature numérique et vérifie sa finitude."""
    if not _is_numeric_value(value):
        raise MLPreprocessingError(f"{feature_name} doit être numérique")

    converted = float(value)

    if not math.isfinite(converted):
        raise MLPreprocessingError(f"{feature_name} doit être fini")

    return converted


def _infer_feature_kind(
    feature_name: str,
    values: Sequence[object],
) -> FeatureKind | None:
    """Déduit le type d'une feature depuis les valeurs non nulles."""
    kinds: set[FeatureKind] = set()

    for value in values:
        if value is None:
            continue

        if isinstance(value, bool):
            kinds.add("boolean")
            continue

        if _is_numeric_value(value):
            _validated_numeric_value(
                feature_name,
                value,
            )
            kinds.add("numeric")
            continue

        if isinstance(value, str):
            kinds.add("categorical")
            continue

        raise MLPreprocessingError(
            f"{feature_name} utilise un type non pris en charge : " f"{type(value).__name__}"
        )

    if not kinds:
        return None

    if kinds == {"numeric"}:
        return "numeric"

    if kinds == {"boolean"}:
        return "boolean"

    if kinds == {"categorical"}:
        return "categorical"

    raise MLPreprocessingError(
        f"{feature_name} utilise plusieurs types incompatibles : " f"{sorted(kinds)}"
    )


def _feature_values(
    rows: Sequence[MLDatasetRow],
    feature_name: str,
) -> tuple[object, ...]:
    """Retourne toutes les valeurs d'une feature, absences incluses."""
    return tuple(row.features.get(feature_name) for row in rows)


def _is_constant_feature(
    feature_name: str,
    kind: FeatureKind | None,
    values: Sequence[object],
) -> bool:
    """Détermine si la feature devient constante après imputation."""
    if kind is None:
        return True

    if kind == "categorical":
        normalized = {(value if value is not None else MISSING_CATEGORY) for value in values}
        return len(normalized) <= 1

    if kind == "numeric" and _uses_zero_for_absence(feature_name):
        normalized_numeric = {
            (
                _validated_numeric_value(
                    feature_name,
                    value,
                )
                if value is not None
                else 0.0
            )
            for value in values
        }
        return len(normalized_numeric) <= 1

    normalized_values: set[
        tuple[str, object]
    ] = set()

    for value in values:
        if value is None:
            normalized_values.add(
                (
                    "missing",
                    None,
                )
            )
            continue

        if kind == "boolean":
            if not isinstance(value, bool):
                raise MLPreprocessingError(
                    f"{feature_name} doit être booléen"
                )

            normalized_values.add(
                (
                    "value",
                    value,
                )
            )
            continue

        normalized_values.add(
            (
                "value",
                _validated_numeric_value(
                    feature_name,
                    value,
                ),
            )
        )

    return len(normalized_values) <= 1


def _analyze_features(
    rows: Sequence[MLDatasetRow],
) -> tuple[
    tuple[str, ...],
    dict[str, FeatureKind],
    tuple[str, ...],
]:
    """Analyse le schéma brut appris exclusivement sur le train."""
    feature_names = tuple(sorted({feature_name for row in rows for feature_name in row.features}))

    if not feature_names:
        raise MLPreprocessingError("aucune feature n'est disponible")

    feature_kinds: dict[str, FeatureKind] = {}
    constant_features: list[str] = []

    for feature_name in feature_names:
        values = _feature_values(
            rows,
            feature_name,
        )
        kind = _infer_feature_kind(
            feature_name,
            values,
        )

        if _is_constant_feature(
            feature_name,
            kind,
            values,
        ):
            constant_features.append(feature_name)
            continue

        if kind is None:
            raise MLPreprocessingError(f"type introuvable pour {feature_name}")

        feature_kinds[feature_name] = kind

    active_feature_names = tuple(
        feature_name for feature_name in feature_names if feature_name in feature_kinds
    )

    if not active_feature_names:
        raise MLPreprocessingError("toutes les features d'entraînement sont constantes")

    return (
        active_feature_names,
        feature_kinds,
        tuple(constant_features),
    )


def _build_input_matrix(
    rows: Sequence[MLDatasetRow],
    active_feature_names: tuple[str, ...],
    feature_kinds: dict[str, FeatureKind],
) -> NDArray[np.object_]:
    """Construit la matrice brute dans l'ordre du schéma appris."""
    matrix = np.empty(
        (
            len(rows),
            len(active_feature_names),
        ),
        dtype=object,
    )

    for row_index, row in enumerate(rows):
        for feature_index, feature_name in enumerate(active_feature_names):
            kind = feature_kinds[feature_name]
            value = row.features.get(feature_name)

            if value is None:
                if kind == "numeric" and _uses_zero_for_absence(feature_name):
                    matrix[
                        row_index,
                        feature_index,
                    ] = 0.0
                elif kind == "categorical":
                    matrix[
                        row_index,
                        feature_index,
                    ] = MISSING_CATEGORY
                else:
                    matrix[
                        row_index,
                        feature_index,
                    ] = np.nan

                continue

            if kind == "numeric":
                matrix[
                    row_index,
                    feature_index,
                ] = _validated_numeric_value(
                    feature_name,
                    value,
                )
                continue

            if kind == "boolean":
                if not isinstance(value, bool):
                    raise MLPreprocessingError(f"{feature_name} doit être booléen")

                matrix[
                    row_index,
                    feature_index,
                ] = float(value)
                continue

            if not isinstance(value, str):
                raise MLPreprocessingError(f"{feature_name} doit être textuel")

            matrix[
                row_index,
                feature_index,
            ] = value

    return matrix


def encode_market_labels(
    rows: Sequence[MLDatasetRow],
) -> NDArray[np.int64]:
    """Encode DOWN, NEUTRAL et UP dans un ordre stable."""
    return np.fromiter(
        (LABEL_TO_INDEX[row.label] for row in rows),
        dtype=np.int64,
        count=len(rows),
    )


def decode_market_labels(
    encoded_labels: Sequence[int],
) -> tuple[MarketDirectionLabel, ...]:
    """Restaure les labels métier depuis leurs indices."""
    decoded: list[MarketDirectionLabel] = []

    for encoded_label in encoded_labels:
        index = int(encoded_label)

        if index < 0 or index >= len(LABEL_ORDER):
            raise MLPreprocessingError(f"indice de label inconnu : {index}")

        decoded.append(LABEL_ORDER[index])

    return tuple(decoded)


class MLFeaturePreprocessor:
    """Prétraite les features selon un schéma appris sur le train."""

    def __init__(self) -> None:
        self._transformer: ColumnTransformer | None = None
        self._schema: MLFeatureSchema | None = None
        self._feature_kinds: dict[
            str,
            FeatureKind,
        ] = {}

    @property
    def schema(self) -> MLFeatureSchema:
        """Retourne le schéma appris."""
        if self._schema is None:
            raise MLPreprocessingError("le prétraitement n'est pas entraîné")

        return self._schema

    def fit(
        self,
        rows: Sequence[MLDatasetRow],
    ) -> MLFeaturePreprocessor:
        """Apprend le schéma et les transformations sur le train."""
        if not rows:
            raise MLPreprocessingError("le train ne peut pas être vide")

        (
            active_feature_names,
            feature_kinds,
            constant_features,
        ) = _analyze_features(rows)

        numeric_feature_names = tuple(
            feature_name
            for feature_name in active_feature_names
            if (
                feature_kinds[feature_name] == "numeric"
                and not _uses_zero_for_absence(feature_name)
            )
        )
        zero_fill_numeric_feature_names = tuple(
            feature_name
            for feature_name in active_feature_names
            if (feature_kinds[feature_name] == "numeric" and _uses_zero_for_absence(feature_name))
        )
        boolean_feature_names = tuple(
            feature_name
            for feature_name in active_feature_names
            if feature_kinds[feature_name] == "boolean"
        )
        categorical_feature_names = tuple(
            feature_name
            for feature_name in active_feature_names
            if feature_kinds[feature_name] == "categorical"
        )

        feature_indexes = {
            feature_name: index for index, feature_name in enumerate(active_feature_names)
        }

        transformers: list[
            tuple[
                str,
                Any,
                list[int],
            ]
        ] = []

        regular_numeric_names = numeric_feature_names + boolean_feature_names

        if regular_numeric_names:
            transformers.append(
                (
                    "numeric",
                    Pipeline(
                        steps=[
                            (
                                "imputer",
                                SimpleImputer(
                                    strategy="median",
                                    add_indicator=True,
                                ),
                            ),
                            (
                                "scaler",
                                StandardScaler(),
                            ),
                        ]
                    ),
                    [feature_indexes[name] for name in regular_numeric_names],
                )
            )

        if zero_fill_numeric_feature_names:
            transformers.append(
                (
                    "zero_numeric",
                    Pipeline(
                        steps=[
                            (
                                "imputer",
                                SimpleImputer(
                                    strategy="constant",
                                    fill_value=0.0,
                                ),
                            ),
                            (
                                "scaler",
                                StandardScaler(),
                            ),
                        ]
                    ),
                    [feature_indexes[name] for name in zero_fill_numeric_feature_names],
                )
            )

        if categorical_feature_names:
            transformers.append(
                (
                    "categorical",
                    Pipeline(
                        steps=[
                            (
                                "imputer",
                                SimpleImputer(
                                    strategy="constant",
                                    fill_value=(MISSING_CATEGORY),
                                ),
                            ),
                            (
                                "one_hot",
                                OneHotEncoder(
                                    handle_unknown="ignore",
                                    sparse_output=False,
                                    dtype=np.float64,
                                ),
                            ),
                        ]
                    ),
                    [feature_indexes[name] for name in categorical_feature_names],
                )
            )

        transformer = ColumnTransformer(
            transformers=transformers,
            remainder="drop",
            sparse_threshold=0.0,
            verbose_feature_names_out=True,
        )

        input_matrix = _build_input_matrix(
            rows,
            active_feature_names,
            feature_kinds,
        )

        transformer.fit(input_matrix)

        output_feature_names = tuple(
            str(name) for name in transformer.get_feature_names_out(active_feature_names)
        )

        if not output_feature_names:
            raise MLPreprocessingError("le prétraitement ne produit aucune colonne")

        self._transformer = transformer
        self._feature_kinds = dict(feature_kinds)
        self._schema = MLFeatureSchema(
            input_feature_names=tuple(
                sorted({feature_name for row in rows for feature_name in row.features})
            ),
            active_feature_names=(active_feature_names),
            dropped_constant_feature_names=(constant_features),
            numeric_feature_names=(numeric_feature_names),
            zero_fill_numeric_feature_names=(zero_fill_numeric_feature_names),
            boolean_feature_names=(boolean_feature_names),
            categorical_feature_names=(categorical_feature_names),
            output_feature_names=(output_feature_names),
        )

        return self

    def transform(
        self,
        rows: Sequence[MLDatasetRow],
    ) -> NDArray[np.float64]:
        """Transforme des lignes sans réapprendre le schéma."""
        transformer = self._transformer
        schema = self._schema

        if transformer is None or schema is None:
            raise MLPreprocessingError("le prétraitement n'est pas entraîné")

        if not rows:
            return np.empty(
                (
                    0,
                    schema.output_feature_count,
                ),
                dtype=np.float64,
            )

        input_matrix = _build_input_matrix(
            rows,
            schema.active_feature_names,
            self._feature_kinds,
        )

        transformed = transformer.transform(input_matrix)
        matrix = np.asarray(
            transformed,
            dtype=np.float64,
        )

        expected_shape = (
            len(rows),
            schema.output_feature_count,
        )

        if matrix.shape != expected_shape:
            raise MLPreprocessingError(
                "forme de matrice inattendue : " f"{matrix.shape}, attendu {expected_shape}"
            )

        if not np.isfinite(matrix).all():
            raise MLPreprocessingError("la matrice transformée contient " "des valeurs non finies")

        return matrix

    def fit_transform(
        self,
        rows: Sequence[MLDatasetRow],
    ) -> NDArray[np.float64]:
        """Apprend sur le train puis le transforme."""
        self.fit(rows)
        return self.transform(rows)
