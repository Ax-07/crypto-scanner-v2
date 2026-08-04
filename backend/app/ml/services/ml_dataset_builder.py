"""Orchestration de la construction d'un dataset ML causal."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import ValidationError

from app.ml.domain.ml_dataset import (
    MLDatasetBuildError,
    build_ml_dataset_row,
    extract_natr_percent,
)
from app.models.backtest import BacktestStatus
from app.ml.models.ml_dataset import MLDatasetRow
from app.repositories.backtest_repository import BacktestRepository

ML_DATASET_HORIZON: Final[Literal[6]] = 6


@dataclass(frozen=True, slots=True)
class MLDatasetBuildReport:
    """Compteurs déterministes d'une construction de dataset."""

    source_rows: int
    processed_rows: int
    generated_rows: int
    skipped_rows: int
    censored_outcomes: int
    invalid_outcomes: int
    missing_natr: int
    contract_rejections: int
    batch_count: int
    rejection_reasons: dict[str, int]


@dataclass(frozen=True, slots=True)
class MLDatasetBuildResult:
    """Dataset construit en mémoire et rapport associé."""

    job_id: str
    horizon: Literal[6]
    natr_multiplier: float
    rows: tuple[MLDatasetRow, ...]
    report: MLDatasetBuildReport


class MLDatasetBuilder:
    """Construit les lignes ML depuis un backtest terminé."""

    def __init__(
        self,
        backtests: BacktestRepository,
    ) -> None:
        self.backtests = backtests

    async def build(
        self,
        job_id: str,
        *,
        batch_size: int = 1_000,
        natr_multiplier: float = 1.0,
    ) -> MLDatasetBuildResult:
        """Parcourt les sources SQLite par lots et construit le dataset.

        Chaque ligne rejetée appartient à une seule catégorie, selon cette
        priorité :

        1. outcome censuré ;
        2. outcome invalide ;
        3. NATR absent ou inutilisable ;
        4. autre rejet du contrat ML.
        """
        normalized_job_id = job_id.strip()

        if not normalized_job_id:
            raise ValueError("job_id ne peut pas être vide")

        if batch_size < 1:
            raise ValueError("batch_size doit être supérieur ou égal à 1")

        if not math.isfinite(natr_multiplier) or natr_multiplier <= 0 or natr_multiplier > 10:
            raise ValueError(
                "natr_multiplier doit être fini, supérieur à zéro " "et inférieur ou égal à 10"
            )

        source_job = await self.backtests.get_job(normalized_job_id)

        if source_job is None or source_job.status != BacktestStatus.COMPLETED:
            raise ValueError("le backtest source doit exister et être terminé")

        generated_rows: list[MLDatasetRow] = []
        rejection_reasons: Counter[str] = Counter()

        source_rows = 0
        processed_rows = 0
        censored_outcomes = 0
        invalid_outcomes = 0
        missing_natr = 0
        contract_rejections = 0
        batch_count = 0
        offset = 0
        source_count_initialized = False

        while True:
            source_batch, total = await self.backtests.ml_source_rows(
                normalized_job_id,
                horizon=ML_DATASET_HORIZON,
                offset=offset,
                limit=batch_size,
            )

            if not source_count_initialized:
                source_rows = total
                source_count_initialized = True

            if not source_batch:
                break

            batch_count += 1

            for observation, outcome in source_batch:
                processed_rows += 1

                if outcome.censored:
                    censored_outcomes += 1
                    continue

                if not outcome.valid:
                    invalid_outcomes += 1
                    continue

                try:
                    extract_natr_percent(observation)
                except MLDatasetBuildError:
                    missing_natr += 1
                    continue

                try:
                    dataset_row = build_ml_dataset_row(
                        observation,
                        outcome,
                        natr_multiplier=natr_multiplier,
                    )
                except (
                    MLDatasetBuildError,
                    ValidationError,
                ) as exc:
                    contract_rejections += 1
                    rejection_reasons[str(exc)] += 1
                    continue

                generated_rows.append(dataset_row)

            offset += len(source_batch)

            if offset >= total:
                break

        skipped_rows = censored_outcomes + invalid_outcomes + missing_natr + contract_rejections

        report = MLDatasetBuildReport(
            source_rows=source_rows,
            processed_rows=processed_rows,
            generated_rows=len(generated_rows),
            skipped_rows=skipped_rows,
            censored_outcomes=censored_outcomes,
            invalid_outcomes=invalid_outcomes,
            missing_natr=missing_natr,
            contract_rejections=contract_rejections,
            batch_count=batch_count,
            rejection_reasons=dict(sorted(rejection_reasons.items())),
        )

        return MLDatasetBuildResult(
            job_id=normalized_job_id,
            horizon=ML_DATASET_HORIZON,
            natr_multiplier=natr_multiplier,
            rows=tuple(generated_rows),
            report=report,
        )
