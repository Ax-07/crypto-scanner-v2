"""Découpage walk-forward expansif des datasets ML."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from app.ml.models.ml_dataset import MLDatasetRow


class MLWalkForwardError(ValueError):
    """Signale qu'un plan walk-forward ne peut pas être construit."""


@dataclass(frozen=True, slots=True)
class MLWalkForwardFold:
    """Une fenêtre d'entraînement et de validation chronologique."""

    fold_index: int

    train_rows: tuple[MLDatasetRow, ...]
    validation_rows: tuple[MLDatasetRow, ...]

    validation_start: datetime
    validation_end: datetime

    purged_before_validation: int

    @property
    def train_row_count(self) -> int:
        """Retourne le nombre de lignes d'entraînement."""
        return len(self.train_rows)

    @property
    def validation_row_count(self) -> int:
        """Retourne le nombre de lignes de validation."""
        return len(self.validation_rows)


@dataclass(frozen=True, slots=True)
class MLWalkForwardPlan:
    """Plan complet de validation walk-forward."""

    folds: tuple[MLWalkForwardFold, ...]

    evaluation_end: datetime
    validation_window: int
    minimum_train_window: int

    source_row_count: int
    eligible_row_count: int

    excluded_at_or_after_evaluation_end: int
    excluded_target_overlap_count: int

    @property
    def fold_count(self) -> int:
        """Retourne le nombre de fenêtres."""
        return len(self.folds)

    @property
    def validation_row_count(self) -> int:
        """Retourne le nombre total de lignes de validation."""
        return sum(fold.validation_row_count for fold in self.folds)


def _validate_positive_integer(
    value: int,
    *,
    name: str,
) -> None:
    """Valide un entier strictement positif."""
    if isinstance(value, bool) or value <= 0:
        raise MLWalkForwardError(f"{name} doit être un entier strictement positif")


def _validate_evaluation_end(
    evaluation_end: datetime,
) -> None:
    """Vérifie que la frontière finale est exprimée en UTC."""
    if evaluation_end.tzinfo is None or evaluation_end.utcoffset() is None:
        raise MLWalkForwardError("evaluation_end doit être timezone-aware")

    if evaluation_end.utcoffset() != timedelta(0):
        raise MLWalkForwardError("evaluation_end doit être exprimé en UTC")


def _ordered_rows(
    rows: Sequence[MLDatasetRow],
) -> tuple[MLDatasetRow, ...]:
    """Trie les lignes et vérifie l'unicité des observations."""
    ordered = tuple(
        sorted(
            rows,
            key=lambda row: (
                row.decision_time,
                row.observation_id,
            ),
        )
    )

    observation_ids: set[int] = set()

    for row in ordered:
        if row.observation_id in observation_ids:
            raise MLWalkForwardError(
                "le dataset contient plusieurs lignes pour " f"l'observation {row.observation_id}"
            )

        observation_ids.add(row.observation_id)

    return ordered


def _validate_dataset_contract(
    rows: tuple[MLDatasetRow, ...],
) -> None:
    """Vérifie les métadonnées communes du dataset."""
    if not rows:
        raise MLWalkForwardError("le dataset ne peut pas être vide")

    job_ids = {row.job_id for row in rows}
    horizons = {row.horizon for row in rows}

    if len(job_ids) != 1:
        raise MLWalkForwardError("toutes les lignes doivent provenir du même job")

    if len(horizons) != 1:
        raise MLWalkForwardError("toutes les lignes doivent utiliser le même horizon")


def build_expanding_walk_forward_plan(
    rows: Sequence[MLDatasetRow],
    *,
    evaluation_end: datetime,
    fold_count: int = 4,
    validation_window: int = 72,
    minimum_train_window: int = 200,
) -> MLWalkForwardPlan:
    """Construit des fenêtres expansives avant une frontière réservée.

    ``evaluation_end`` correspond au début de la partition de test.
    Toute ligne décidée à partir de cette frontière est exclue.

    Une ligne antérieure dont la cible atteint ou dépasse cette frontière
    est également exclue afin que la sélection du modèle n'utilise aucun
    mouvement de prix appartenant à la période de test.

    Pour chaque fenêtre, les lignes d'entraînement dont ``exit_time``
    atteint ou dépasse le début de validation sont purgées.
    """
    _validate_positive_integer(
        fold_count,
        name="fold_count",
    )
    _validate_positive_integer(
        validation_window,
        name="validation_window",
    )
    _validate_positive_integer(
        minimum_train_window,
        name="minimum_train_window",
    )
    _validate_evaluation_end(evaluation_end)

    ordered = _ordered_rows(rows)
    _validate_dataset_contract(ordered)

    excluded_at_or_after = tuple(row for row in ordered if row.decision_time >= evaluation_end)
    pre_evaluation_rows = tuple(row for row in ordered if row.decision_time < evaluation_end)
    excluded_target_overlap = tuple(
        row for row in pre_evaluation_rows if row.exit_time >= evaluation_end
    )
    eligible_rows = tuple(row for row in pre_evaluation_rows if row.exit_time < evaluation_end)

    decision_times = tuple(sorted({row.decision_time for row in eligible_rows}))

    required_validation_times = fold_count * validation_window
    required_time_count = minimum_train_window + required_validation_times

    if len(decision_times) < required_time_count:
        raise MLWalkForwardError(
            "nombre de temps de décision insuffisant : "
            f"{len(decision_times)}, "
            f"minimum requis {required_time_count}"
        )

    first_validation_index = len(decision_times) - required_validation_times

    if first_validation_index < minimum_train_window:
        raise MLWalkForwardError(
            "la première fenêtre ne dispose pas " "d'un historique d'entraînement suffisant"
        )

    folds: list[MLWalkForwardFold] = []

    for offset in range(fold_count):
        validation_start_index = first_validation_index + offset * validation_window
        validation_end_index = validation_start_index + validation_window

        validation_times = decision_times[validation_start_index:validation_end_index]

        if len(validation_times) != validation_window:
            raise MLWalkForwardError("fenêtre de validation incomplète")

        validation_start = validation_times[0]
        validation_end = validation_times[-1]

        train_candidates = tuple(
            row for row in eligible_rows if row.decision_time < validation_start
        )
        train_rows = tuple(row for row in train_candidates if row.exit_time < validation_start)
        validation_rows = tuple(
            row
            for row in eligible_rows
            if (validation_start <= row.decision_time <= validation_end)
        )

        purged_before_validation = len(train_candidates) - len(train_rows)

        if not train_rows:
            raise MLWalkForwardError(f"le train du fold {offset + 1} " "est vide après purge")

        if not validation_rows:
            raise MLWalkForwardError(f"la validation du fold {offset + 1} " "est vide")

        if train_rows[-1].exit_time >= validation_start:
            raise MLWalkForwardError(f"le fold {offset + 1} contient " "une fuite temporelle")

        folds.append(
            MLWalkForwardFold(
                fold_index=offset + 1,
                train_rows=train_rows,
                validation_rows=validation_rows,
                validation_start=validation_start,
                validation_end=validation_end,
                purged_before_validation=(purged_before_validation),
            )
        )

    validation_observation_ids = [
        row.observation_id for fold in folds for row in fold.validation_rows
    ]

    if len(validation_observation_ids) != len(set(validation_observation_ids)):
        raise MLWalkForwardError("les fenêtres de validation se chevauchent")

    return MLWalkForwardPlan(
        folds=tuple(folds),
        evaluation_end=evaluation_end,
        validation_window=validation_window,
        minimum_train_window=minimum_train_window,
        source_row_count=len(ordered),
        eligible_row_count=len(eligible_rows),
        excluded_at_or_after_evaluation_end=len(excluded_at_or_after),
        excluded_target_overlap_count=len(excluded_target_overlap),
    )
