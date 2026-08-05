from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from app.models.backtest import (
    BacktestConfig,
    BacktestJob,
    BacktestStatus,
    ForwardOutcome,
    SignalObservation,
)
from app.ml.models.ml_dataset import (
    ML_FEATURE_SCHEMA_VERSION,
    ML_FEATURE_SCHEMA_VERSION_V2,
    MLFeatureSchemaVersion,
    MarketDirectionLabel,
)
from app.core.settings import ScanConfig
from app.ml.domain.ml_dataset_profile import (
    ML_DATASET_PROFILE_V2_ID,
    build_ml_dataset_profile_v2,
)
from app.repositories.backtest_repository import BacktestRepository
from app.ml.services.ml_dataset_builder import MLDatasetBuilder

JOB_ID = "ml-service-test"
DECISION_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
PROFILE_FINGERPRINT_A = "sha256:" + ("a" * 64)
PROFILE_FINGERPRINT_B = "sha256:" + ("b" * 64)
DEFAULT_PROFILE_FINGERPRINT = object()


class FakeBacktestRepository:
    """Double minimal isolant l'orchestration du service."""

    def __init__(
        self,
        job: BacktestJob | None,
        rows: list[tuple[SignalObservation, ForwardOutcome]],
    ) -> None:
        self.job = job
        self.rows = rows
        self.calls: list[tuple[int, int, int]] = []
        self.get_job_calls: list[str] = []

    async def get_job(
        self,
        job_id: str,
    ) -> BacktestJob | None:
        self.get_job_calls.append(job_id)
        return self.job

    async def ml_source_rows(
        self,
        job_id: str,
        *,
        horizon: int = 6,
        offset: int = 0,
        limit: int = 1_000,
    ) -> tuple[
        list[tuple[SignalObservation, ForwardOutcome]],
        int,
    ]:
        assert job_id == JOB_ID

        self.calls.append(
            (
                horizon,
                offset,
                limit,
            )
        )

        return (
            self.rows[offset : offset + limit],
            len(self.rows),
        )


def completed_job(
    *,
    status: BacktestStatus = BacktestStatus.COMPLETED,
    signal_profile_id: str = "inline",
    signal_config: ScanConfig | None = None,
) -> BacktestJob:
    """Construit un backtest source minimal."""
    return BacktestJob(
        id=JOB_ID,
        status=status,
        config=BacktestConfig(
            symbols=["BTC/USDC"],
            start=DECISION_TIME - timedelta(days=1),
            end=DECISION_TIME + timedelta(days=1),
            signal_config=signal_config or ScanConfig(),
            signal_profile_id=signal_profile_id,
            horizons=[6],
        ),
    )


def observation(
    observation_id: int,
    *,
    with_natr: bool = True,
    profile_id: str = "inline",
    profile_fingerprint: str | None | object = (DEFAULT_PROFILE_FINGERPRINT),
) -> SignalObservation:
    """Construit une observation confirmée persistée."""
    indicator_signals: dict[str, object] = {}

    if with_natr:
        indicator_signals["atr"] = {
            "status": "available",
            "direction": "neutral",
            "signal": None,
            "state": "stable",
            "strength": 0.0,
            "reason": None,
            "raw_value": 2.0,
            "components": {
                "natr": {
                    "value": 2.0,
                    "normalized_value": 0.02,
                    "unit": "percent",
                },
            },
        }

    resolved_profile_fingerprint = (
        PROFILE_FINGERPRINT_A
        if profile_fingerprint is DEFAULT_PROFILE_FINGERPRINT
        else profile_fingerprint
    )

    return SignalObservation.model_validate(
        {
            "id": observation_id,
            "job_id": JOB_ID,
            "symbol": "BTC/USDC",
            "timeframe": "1h",
            "decision_time": (DECISION_TIME + timedelta(hours=observation_id)),
            "source_open_time": (DECISION_TIME + timedelta(hours=observation_id - 1)),
            "snapshot_status": "confirmed",
            "accepted": True,
            "close": 100.0,
            "indicator_signals": indicator_signals,
            "algorithm_version": "signal-evaluation-v3",
            "dataset_version": "service-test-v1",
            "profile_id": profile_id,
            "profile_fingerprint": resolved_profile_fingerprint,
        }
    )


def outcome(
    observation_id: int,
    *,
    gross_return: float | None = 0.03,
    censored: bool = False,
    valid: bool = True,
) -> ForwardOutcome:
    """Construit un outcome à six bougies."""
    decision_time = DECISION_TIME + timedelta(hours=observation_id)

    return ForwardOutcome(
        observation_id=observation_id,
        horizon=6,
        entry_policy="signal_close",
        entry_time=decision_time,
        entry_price=100.0,
        exit_time=decision_time + timedelta(hours=6),
        exit_price=(100.0 * (1 + gross_return) if gross_return is not None else None),
        gross_return=gross_return,
        censored=censored,
        censor_reason=("end_of_history" if censored else None),
        available_bars=6,
        valid=valid,
    )


def service_for(
    repository: FakeBacktestRepository,
) -> MLDatasetBuilder:
    """Adapte le double au type concret injecté par le service."""
    return MLDatasetBuilder(
        cast(
            BacktestRepository,
            repository,
        )
    )


@pytest.mark.asyncio
async def test_builder_service_batches_and_counts_rejections() -> None:
    rows = [
        (
            observation(1),
            outcome(
                1,
                gross_return=0.03,
            ),
        ),
        (
            observation(2),
            outcome(
                2,
                censored=True,
            ),
        ),
        (
            observation(3),
            outcome(
                3,
                valid=False,
            ),
        ),
        (
            observation(
                4,
                with_natr=False,
            ),
            outcome(4),
        ),
        (
            observation(5),
            outcome(
                5,
                gross_return=None,
            ),
        ),
        (
            observation(6),
            outcome(
                6,
                gross_return=0.01,
            ),
        ),
    ]

    repository = FakeBacktestRepository(
        completed_job(),
        rows,
    )

    result = await service_for(repository).build(
        JOB_ID,
        batch_size=2,
    )

    assert repository.get_job_calls == [JOB_ID]
    assert repository.calls == [
        (
            6,
            0,
            2,
        ),
        (
            6,
            2,
            2,
        ),
        (
            6,
            4,
            2,
        ),
    ]

    assert result.job_id == JOB_ID
    assert result.horizon == 6
    assert result.natr_multiplier == pytest.approx(1.0)
    assert result.feature_schema_version == ML_FEATURE_SCHEMA_VERSION
    assert len(result.rows) == 2
    assert [row.observation_id for row in result.rows] == [
        1,
        6,
    ]
    assert [row.label for row in result.rows] == [
        MarketDirectionLabel.UP,
        MarketDirectionLabel.NEUTRAL,
    ]
    assert all(row.feature_schema_version == ML_FEATURE_SCHEMA_VERSION for row in result.rows)

    report = result.report

    assert report.source_rows == 6
    assert report.processed_rows == 6
    assert report.generated_rows == 2
    assert report.skipped_rows == 4

    assert report.censored_outcomes == 1
    assert report.invalid_outcomes == 1
    assert report.missing_natr == 1
    assert report.contract_rejections == 1
    assert report.batch_count == 3

    assert report.generated_rows + report.skipped_rows == report.processed_rows

    assert sum(report.rejection_reasons.values()) == 1
    assert any("gross_return est requis" in reason for reason in report.rejection_reasons)


@pytest.mark.asyncio
async def test_builder_service_propagates_v2_feature_schema() -> None:
    repository = FakeBacktestRepository(
        completed_job(
            signal_profile_id=ML_DATASET_PROFILE_V2_ID,
            signal_config=build_ml_dataset_profile_v2(
                timeframe="1h",
            ),
        ),
        [
            (
                observation(
                    1,
                    profile_id=ML_DATASET_PROFILE_V2_ID,
                    profile_fingerprint=PROFILE_FINGERPRINT_A,
                ),
                outcome(1),
            ),
        ],
    )

    result = await service_for(repository).build(
        JOB_ID,
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    assert result.feature_schema_version == ML_FEATURE_SCHEMA_VERSION_V2
    assert len(result.rows) == 1
    assert result.rows[0].feature_schema_version == (ML_FEATURE_SCHEMA_VERSION_V2)
    assert result.rows[0].profile_id == ML_DATASET_PROFILE_V2_ID
    assert result.rows[0].profile_fingerprint == PROFILE_FINGERPRINT_A


@pytest.mark.asyncio
async def test_builder_service_rejects_v2_from_inline_job() -> None:
    repository = FakeBacktestRepository(
        completed_job(),
        [],
    )

    with pytest.raises(
        ValueError,
        match="signal_profile_id",
    ):
        await service_for(repository).build(
            JOB_ID,
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
        )

    assert repository.calls == []


@pytest.mark.asyncio
async def test_builder_service_rejects_noncanonical_v2_profile() -> None:
    repository = FakeBacktestRepository(
        completed_job(
            signal_profile_id=ML_DATASET_PROFILE_V2_ID,
            signal_config=ScanConfig(
                timeframe="1h",
            ),
        ),
        [],
    )

    with pytest.raises(
        ValueError,
        match="profil technique canonique",
    ):
        await service_for(repository).build(
            JOB_ID,
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
        )

    assert repository.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile_id", "profile_fingerprint", "message"),
    [
        (
            "inline",
            PROFILE_FINGERPRINT_A,
            "profile_id",
        ),
        (
            ML_DATASET_PROFILE_V2_ID,
            None,
            "profile_fingerprint",
        ),
        (
            ML_DATASET_PROFILE_V2_ID,
            "sha256:invalid",
            "profile_fingerprint",
        ),
    ],
)
async def test_builder_service_rejects_invalid_v2_observation_provenance(
    profile_id: str,
    profile_fingerprint: str | None,
    message: str,
) -> None:
    repository = FakeBacktestRepository(
        completed_job(
            signal_profile_id=ML_DATASET_PROFILE_V2_ID,
            signal_config=build_ml_dataset_profile_v2(
                timeframe="1h",
            ),
        ),
        [
            (
                observation(
                    1,
                    profile_id=profile_id,
                    profile_fingerprint=profile_fingerprint,
                ),
                outcome(1),
            ),
        ],
    )

    with pytest.raises(
        ValueError,
        match=message,
    ):
        await service_for(repository).build(
            JOB_ID,
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
        )


@pytest.mark.asyncio
async def test_builder_service_rejects_mixed_v2_fingerprints() -> None:
    repository = FakeBacktestRepository(
        completed_job(
            signal_profile_id=ML_DATASET_PROFILE_V2_ID,
            signal_config=build_ml_dataset_profile_v2(
                timeframe="1h",
            ),
        ),
        [
            (
                observation(
                    1,
                    profile_id=ML_DATASET_PROFILE_V2_ID,
                    profile_fingerprint=PROFILE_FINGERPRINT_A,
                ),
                outcome(1),
            ),
            (
                observation(
                    2,
                    profile_id=ML_DATASET_PROFILE_V2_ID,
                    profile_fingerprint=PROFILE_FINGERPRINT_B,
                ),
                outcome(2),
            ),
        ],
    )

    with pytest.raises(
        ValueError,
        match="plusieurs profile_fingerprints",
    ):
        await service_for(repository).build(
            JOB_ID,
            batch_size=1,
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
        )


@pytest.mark.asyncio
async def test_builder_service_rejects_empty_v2_dataset() -> None:
    repository = FakeBacktestRepository(
        completed_job(
            signal_profile_id=ML_DATASET_PROFILE_V2_ID,
            signal_config=build_ml_dataset_profile_v2(
                timeframe="1h",
            ),
        ),
        [],
    )

    with pytest.raises(
        ValueError,
        match="sans ligne ML exploitable",
    ):
        await service_for(repository).build(
            JOB_ID,
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
        )


@pytest.mark.asyncio
async def test_builder_service_applies_natr_multiplier() -> None:
    repository = FakeBacktestRepository(
        completed_job(),
        [
            (
                observation(1),
                outcome(
                    1,
                    gross_return=0.025,
                ),
            ),
        ],
    )

    result = await service_for(repository).build(
        JOB_ID,
        natr_multiplier=1.5,
    )

    assert len(result.rows) == 1

    row = result.rows[0]

    assert row.natr_multiplier == pytest.approx(1.5)
    assert row.neutral_threshold_return == pytest.approx(0.03)
    assert row.label is MarketDirectionLabel.NEUTRAL


@pytest.mark.asyncio
async def test_builder_service_rejects_unknown_feature_schema() -> None:
    repository = FakeBacktestRepository(
        completed_job(),
        [],
    )

    invalid_schema = cast(
        MLFeatureSchemaVersion,
        "causal-features-v999",
    )

    with pytest.raises(
        ValueError,
        match="feature_schema_version",
    ):
        await service_for(repository).build(
            JOB_ID,
            feature_schema_version=invalid_schema,
        )

    assert repository.get_job_calls == []
    assert repository.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job",
    [
        None,
        completed_job(
            status=BacktestStatus.PENDING,
        ),
        completed_job(
            status=BacktestStatus.RUNNING,
        ),
        completed_job(
            status=BacktestStatus.FAILED,
        ),
    ],
)
async def test_builder_service_requires_completed_job(
    job: BacktestJob | None,
) -> None:
    repository = FakeBacktestRepository(
        job,
        [],
    )

    with pytest.raises(
        ValueError,
        match="doit exister et être terminé",
    ):
        await service_for(repository).build(JOB_ID)

    assert repository.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_id", "batch_size", "multiplier", "message"),
    [
        (
            "   ",
            1,
            1.0,
            "job_id",
        ),
        (
            JOB_ID,
            0,
            1.0,
            "batch_size",
        ),
        (
            JOB_ID,
            1,
            0.0,
            "natr_multiplier",
        ),
        (
            JOB_ID,
            1,
            -1.0,
            "natr_multiplier",
        ),
        (
            JOB_ID,
            1,
            10.1,
            "natr_multiplier",
        ),
        (
            JOB_ID,
            1,
            float("inf"),
            "natr_multiplier",
        ),
        (
            JOB_ID,
            1,
            float("nan"),
            "natr_multiplier",
        ),
    ],
)
async def test_builder_service_rejects_invalid_arguments(
    job_id: str,
    batch_size: int,
    multiplier: float,
    message: str,
) -> None:
    repository = FakeBacktestRepository(
        completed_job(),
        [],
    )

    with pytest.raises(
        ValueError,
        match=message,
    ):
        await service_for(repository).build(
            job_id,
            batch_size=batch_size,
            natr_multiplier=multiplier,
        )

    assert repository.get_job_calls == []
    assert repository.calls == []


@pytest.mark.asyncio
async def test_builder_service_handles_empty_source() -> None:
    repository = FakeBacktestRepository(
        completed_job(),
        [],
    )

    result = await service_for(repository).build(
        JOB_ID,
        batch_size=5,
    )

    assert repository.calls == [
        (
            6,
            0,
            5,
        ),
    ]

    assert result.rows == ()
    assert result.report.source_rows == 0
    assert result.report.processed_rows == 0
    assert result.report.generated_rows == 0
    assert result.report.skipped_rows == 0
    assert result.report.batch_count == 0
    assert result.report.rejection_reasons == {}
