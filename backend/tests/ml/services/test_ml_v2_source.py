from __future__ import annotations

import asyncio
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database.connection import Database
from app.domain.candles import Candle, timeframe_milliseconds
from app.domain.backtesting import signal_profile_fingerprint
from app.ml.domain.ml_dataset_profile import (
    ML_DATASET_PROFILE_V2_ID,
    build_ml_dataset_profile_v2,
)
from app.ml.models.ml_dataset import ML_FEATURE_SCHEMA_VERSION_V2
from app.ml.services.ml_dataset_builder import MLDatasetBuilder
from app.ml.services.ml_dataset_exporter import MLDatasetExporter
from app.ml.services.ml_dataset_loader import MLDatasetLoader
from app.ml.services.ml_v2_source import (
    MLV2SourceCoverageError,
    MLV2SourceService,
    build_ml_v2_source_config,
    ml_v2_source_identity,
)
from app.models.backtest import (
    SIGNAL_EVALUATION_VERSION,
    BacktestJob,
    BacktestStatus,
    SignalObservation,
)
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_manager import BacktestManager

SYMBOL = "SYN/USDC"
START_MS = 1_700_000_000_000
MINUTE = 60_000


def source_config(*, start_ms: int = START_MS, end_ms: int = START_MS + 10 * MINUTE):
    return build_ml_v2_source_config(
        symbol=SYMBOL,
        timeframe="1m",
        start=datetime.fromtimestamp(start_ms / 1_000, tz=timezone.utc),
        end=datetime.fromtimestamp(end_ms / 1_000, tz=timezone.utc),
    )


def candle(timeframe: str, open_time: int, index: int) -> Candle:
    close = 100 + index * 0.03 + math.sin(index / 7)
    return Candle(
        exchange_id="binance",
        market_type="spot",
        symbol=SYMBOL,
        timeframe=timeframe,
        open_time=open_time,
        open=close - 0.1,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1_000 + index,
        close_time=open_time + timeframe_milliseconds(timeframe),
        is_closed=True,
    )


async def seed_canonical_history(candles: CandleRepository) -> None:
    primary_start = START_MS - 200 * MINUTE
    await candles.upsert_many(
        [candle("1m", primary_start + index * MINUTE, index) for index in range(217)]
    )
    for timeframe in ("4h", "1d", "1w"):
        interval = timeframe_milliseconds(timeframe)
        await candles.upsert_many(
            [candle(timeframe, START_MS + (index - 60) * interval, index) for index in range(61)]
        )


def test_canonical_config_is_deterministic_and_uses_official_profile() -> None:
    first = source_config()
    second = source_config()
    expected = build_ml_dataset_profile_v2(timeframe="1m", quote="USDC")

    assert first == second
    assert first.signal_profile_id == ML_DATASET_PROFILE_V2_ID
    assert first.signal_config == expected
    assert first.horizons == [6]
    assert first.replay_mode == "every_bar"
    assert first.entry_policy == "signal_close"
    assert first.gap_policy == "reject_range"
    assert first.snapshot_status == "confirmed"
    assert first.portfolio_simulation is None
    assert ml_v2_source_identity(first) == ml_v2_source_identity(second)


def test_source_identity_covers_every_observation_or_label_input() -> None:
    config = source_config()
    variants = (
        config.model_copy(update={"end": config.end.replace(minute=config.end.minute + 1)}),
        config.model_copy(update={"entry_policy": "next_open"}),
        config.model_copy(update={"horizons": [6, 12]}),
        config.model_copy(
            update={
                "signal_config": config.signal_config.model_copy(
                    update={"min_confluence_score": 61}
                )
            }
        ),
    )
    identity = ml_v2_source_identity(config)
    assert all(ml_v2_source_identity(item) != identity for item in variants)


@pytest.mark.asyncio
async def test_coverage_failure_is_structured_and_does_not_create_job() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "missing.sqlite3")
        await database.initialize()
        backtests = BacktestRepository(database)
        candles = CandleRepository(database)
        manager = BacktestManager(backtests, candles)

        with pytest.raises(MLV2SourceCoverageError) as raised:
            await MLV2SourceService(backtests, candles, manager).prepare(source_config())

        assert raised.value.diagnostics
        assert any(item.name == "primary-warmup" for item in raised.value.diagnostics)
        _, count = await backtests.list_jobs()
        assert count == 0
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [BacktestStatus.PENDING, BacktestStatus.RUNNING])
async def test_active_source_is_not_duplicated(status: BacktestStatus) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "pending.sqlite3")
        await database.initialize()
        backtests = BacktestRepository(database)
        candles = CandleRepository(database)
        manager = BacktestManager(backtests, candles)
        config = source_config()
        job = BacktestJob(id=f"{status.value}-source", config=config, status=status)
        await backtests.claim_ml_v2_source(
            ml_v2_source_identity(config),
            job,
            algorithm_version=SIGNAL_EVALUATION_VERSION,
        )

        result = await MLV2SourceService(backtests, candles, manager).prepare(config)

        assert result.action == "already-running"
        assert result.job is not None and result.job.id == job.id
        _, count = await backtests.list_jobs()
        assert count == 1
        await database.close()


@pytest.mark.asyncio
async def test_interrupted_compatible_source_is_resumable_in_preview() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "interrupted.sqlite3")
        await database.initialize()
        backtests = BacktestRepository(database)
        candles = CandleRepository(database)
        await seed_canonical_history(candles)
        manager = BacktestManager(backtests, candles)
        config = source_config()
        job = BacktestJob(id="interrupted-source", config=config, status=BacktestStatus.INTERRUPTED)
        await backtests.claim_ml_v2_source(
            ml_v2_source_identity(config),
            job,
            algorithm_version=SIGNAL_EVALUATION_VERSION,
        )
        await backtests.save_checkpoint(
            job.id,
            {
                "algorithm_version": SIGNAL_EVALUATION_VERSION,
                "dataset_version": "sha256:" + "a" * 64,
                "status": "running",
            },
        )

        result = await MLV2SourceService(backtests, candles, manager).prepare(config, dry_run=True)

        assert result.action == "would-resume"
        assert result.job is not None and result.job.id == job.id
        assert result.coverage
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [BacktestStatus.FAILED, BacktestStatus.CANCELLED])
async def test_failed_or_cancelled_source_is_explicitly_replaced_in_preview(
    status: BacktestStatus,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / f"{status.value}.sqlite3")
        await database.initialize()
        backtests = BacktestRepository(database)
        candles = CandleRepository(database)
        await seed_canonical_history(candles)
        manager = BacktestManager(backtests, candles)
        config = source_config()
        job = BacktestJob(id=f"{status.value}-source", config=config, status=status)
        await backtests.claim_ml_v2_source(
            ml_v2_source_identity(config),
            job,
            algorithm_version=SIGNAL_EVALUATION_VERSION,
        )

        result = await MLV2SourceService(backtests, candles, manager).prepare(config, dry_run=True)

        assert result.action == "would-create"
        assert status.value in result.reason
        assert result.job is not None and result.job.id == job.id
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_observation", [False, True])
async def test_incomplete_completed_source_is_not_reused(with_observation: bool) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "empty-completed.sqlite3")
        await database.initialize()
        backtests = BacktestRepository(database)
        candles = CandleRepository(database)
        await seed_canonical_history(candles)
        manager = BacktestManager(backtests, candles)
        config = source_config()
        job = BacktestJob(id="empty-completed", config=config, status=BacktestStatus.COMPLETED)
        await backtests.claim_ml_v2_source(
            ml_v2_source_identity(config),
            job,
            algorithm_version=SIGNAL_EVALUATION_VERSION,
        )
        if with_observation:
            await backtests.add_observation(
                SignalObservation(
                    job_id=job.id,
                    symbol=SYMBOL,
                    timeframe="1m",
                    decision_time=config.start,
                    close=100,
                    accepted=True,
                    profile_id=ML_DATASET_PROFILE_V2_ID,
                    profile_fingerprint=signal_profile_fingerprint(config.signal_config),
                )
            )

        result = await MLV2SourceService(backtests, candles, manager).prepare(config, dry_run=True)

        assert result.action == "would-create"
        assert "inexploitable" in result.reason
        if with_observation:
            observations = await backtests.all_observations(job.id)
            assert observations
            assert await backtests.all_outcomes(job.id) == []
        await database.close()


@pytest.mark.asyncio
async def test_atomic_claim_allows_only_one_concurrent_source() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "concurrent.sqlite3")
        await database.initialize()
        repo_a = BacktestRepository(database)
        repo_b = BacktestRepository(database)
        candles = CandleRepository(database)
        await seed_canonical_history(candles)
        config = source_config()
        identity = ml_v2_source_identity(config)
        manager_a = BacktestManager(repo_a, candles)
        manager_b = BacktestManager(repo_b, candles)

        first, second = await asyncio.gather(
            manager_a.create_ml_v2_source_job(config, identity),
            manager_b.create_ml_v2_source_job(config, identity),
        )

        assert sum((first[1], second[1])) == 1
        assert first[0].id == second[0].id
        winner = manager_a if first[1] else manager_b
        terminal = await winner.wait_until_terminal(first[0].id)
        assert terminal.status == BacktestStatus.COMPLETED
        _, count = await repo_a.list_jobs()
        assert count == 1
        await database.close()


@pytest.mark.asyncio
async def test_end_to_end_source_reuse_export_and_loader() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        database = Database(root / "e2e.sqlite3")
        await database.initialize()
        backtests = BacktestRepository(database)
        candles = CandleRepository(database)
        await seed_canonical_history(candles)
        manager = BacktestManager(backtests, candles)
        service = MLV2SourceService(backtests, candles, manager)
        config = source_config()

        created = await service.prepare(config)
        reused = await service.prepare(config)

        assert created.action == "created"
        assert created.job is not None
        assert created.job.status == BacktestStatus.COMPLETED
        assert created.job.config.signal_config == build_ml_dataset_profile_v2(
            timeframe="1m", quote="USDC"
        )
        assert created.job.config_fingerprint is None
        assert reused.action == "reused"
        assert reused.job is not None and reused.job.id == created.job.id
        observations = await backtests.all_observations(created.job.id)
        outcomes = await backtests.all_outcomes(created.job.id)
        assert observations
        assert any(item.horizon == 6 and not item.censored for item in outcomes)
        expected_profile_fingerprint = signal_profile_fingerprint(config.signal_config)
        assert {item.profile_id for item in observations} == {ML_DATASET_PROFILE_V2_ID}
        assert {item.profile_fingerprint for item in observations} == {expected_profile_fingerprint}

        built = await MLDatasetBuilder(backtests).build(
            created.job.id,
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
        )
        assert built.rows
        exporter = MLDatasetExporter()
        first_export = exporter.export(built, root / "exports", file_stem="first")
        second_export = exporter.export(built, root / "exports", file_stem="second")
        first_loaded = MLDatasetLoader().load(first_export.manifest_path)
        second_loaded = MLDatasetLoader().load(second_export.manifest_path)

        assert first_loaded.rows == second_loaded.rows
        assert first_export.manifest.data_sha256 == second_export.manifest.data_sha256
        assert first_export.data_path.read_bytes() == second_export.data_path.read_bytes()
        assert first_export.manifest.data_sha256.startswith("sha256:")
        _, count = await backtests.list_jobs()
        assert count == 1
        await database.close()
