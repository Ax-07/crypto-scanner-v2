"""Découpage chronologique purgé des datasets ML."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from app.models.ml_dataset import MLDatasetRow


class MLTemporalSplitError(ValueError):
    """Signale qu'un dataset ne peut pas être découpé sans fuite temporelle."""


@dataclass(frozen=True, slots=True)
class MLTemporalSplit:
    """Partitions chronologiques mutuellement exclusives."""

    train_rows: tuple[MLDatasetRow, ...]
    validation_rows: tuple[MLDatasetRow, ...]
    test_rows: tuple[MLDatasetRow, ...]

    validation_start: datetime
    test_start: datetime

    purged_before_validation: int
    purged_before_test: int

    @property
    def source_row_count(self) -> int:
        """Retourne le nombre de lignes avant purge."""
        return (
            len(self.train_rows)
            + len(self.validation_rows)
            + len(self.test_rows)
            + self.purged_before_validation
            + self.purged_before_test
        )

    @property
    def retained_row_count(self) -> int:
        """Retourne le nombre de lignes conservées."""
        return len(self.train_rows) + len(self.validation_rows) + len(self.test_rows)


def _validate_ratios(
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> None:
    """Valide les proportions du découpage."""
    ratios = (
        train_ratio,
        validation_ratio,
        test_ratio,
    )

    if any(not math.isfinite(value) or value <= 0 for value in ratios):
        raise MLTemporalSplitError("les proportions doivent être finies et strictement positives")

    if not math.isclose(
        sum(ratios),
        1.0,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise MLTemporalSplitError(
            "train_ratio + validation_ratio + test_ratio " "doit être égal à 1"
        )


def _ordered_rows(
    rows: tuple[MLDatasetRow, ...],
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
            raise MLTemporalSplitError(
                "le dataset contient plusieurs lignes pour " f"l'observation {row.observation_id}"
            )

        observation_ids.add(row.observation_id)

    return ordered


def split_ml_dataset_chronologically(
    rows: tuple[MLDatasetRow, ...],
    *,
    train_ratio: float = 0.60,
    validation_ratio: float = 0.20,
    test_ratio: float = 0.20,
) -> MLTemporalSplit:
    """Découpe un dataset ML sans chevauchement des cibles futures.

    Les frontières sont déterminées à partir des temps de décision uniques.
    Une même date ne peut donc jamais être répartie entre deux partitions.

    Les lignes d'entraînement dont ``exit_time`` atteint ou dépasse le début
    de la validation sont purgées. La même règle est appliquée entre la
    validation et le test.
    """
    _validate_ratios(
        train_ratio,
        validation_ratio,
        test_ratio,
    )

    ordered = _ordered_rows(rows)

    if len(ordered) < 3:
        raise MLTemporalSplitError("au moins trois lignes sont nécessaires")

    job_ids = {row.job_id for row in ordered}
    horizons = {row.horizon for row in ordered}

    if len(job_ids) != 1:
        raise MLTemporalSplitError("toutes les lignes doivent provenir du même job")

    if len(horizons) != 1:
        raise MLTemporalSplitError("toutes les lignes doivent utiliser le même horizon")

    decision_times = tuple(sorted({row.decision_time for row in ordered}))

    if len(decision_times) < 3:
        raise MLTemporalSplitError("au moins trois temps de décision distincts sont nécessaires")

    time_count = len(decision_times)

    train_cut = int(time_count * train_ratio)
    validation_cut = int(time_count * (train_ratio + validation_ratio))

    train_cut = min(
        max(train_cut, 1),
        time_count - 2,
    )
    validation_cut = min(
        max(validation_cut, train_cut + 1),
        time_count - 1,
    )

    validation_start = decision_times[train_cut]
    test_start = decision_times[validation_cut]

    train_candidates = tuple(row for row in ordered if row.decision_time < validation_start)
    validation_candidates = tuple(
        row for row in ordered if validation_start <= row.decision_time < test_start
    )
    test_rows = tuple(row for row in ordered if row.decision_time >= test_start)

    train_rows = tuple(row for row in train_candidates if row.exit_time < validation_start)
    validation_rows = tuple(row for row in validation_candidates if row.exit_time < test_start)

    purged_before_validation = len(train_candidates) - len(train_rows)
    purged_before_test = len(validation_candidates) - len(validation_rows)

    if not train_rows:
        raise MLTemporalSplitError("la partition d'entraînement est vide après purge")

    if not validation_rows:
        raise MLTemporalSplitError("la partition de validation est vide après purge")

    if not test_rows:
        raise MLTemporalSplitError("la partition de test est vide")

    if train_rows[-1].exit_time >= validation_start:
        raise MLTemporalSplitError("une cible d'entraînement chevauche la validation")

    if validation_rows[-1].exit_time >= test_start:
        raise MLTemporalSplitError("une cible de validation chevauche le test")

    return MLTemporalSplit(
        train_rows=train_rows,
        validation_rows=validation_rows,
        test_rows=test_rows,
        validation_start=validation_start,
        test_start=test_start,
        purged_before_validation=(purged_before_validation),
        purged_before_test=(purged_before_test),
    )
