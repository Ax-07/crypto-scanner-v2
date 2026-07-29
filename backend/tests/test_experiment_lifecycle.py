"""Promotion explicite, rollback et persistance shadow de phase 4."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from app.api.experiments import PromotionRequest, promote
from app.core.settings import ScanConfig
from app.database.connection import Database
from app.models.backtest import BacktestStatus
from app.models.experiment import (
    CandidateResult,
    ExperimentConfig,
    ExperimentManifest,
    ProfileStatus,
    ShadowComparison,
    SignalProfileVersion,
)
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.experiment_repository import ExperimentRepository
from app.services.experiment_manager import ExperimentManager
from app.services.shadow_evaluation import ShadowEvaluationService
from tests.fixtures.synthetic_backtest_v1 import candles


def profile(identifier: str, status: ProfileStatus, experiment_id: str | None = None):
    return SignalProfileVersion(
        id=identifier,
        name=identifier,
        version="1.0.0",
        description="profil synthétique contrôlé",
        signal_config=ScanConfig(),
        experiment_id=experiment_id,
        dataset_version="synthetic-v1",
        code_version="test",
        status=status,
    )


@pytest.mark.asyncio
async def test_promotion_refusal_acceptance_rollback_and_shadow_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "phase4.sqlite3")
        await database.initialize()
        repository = ExperimentRepository(database)
        experiment_id = "experiment-controlled"
        config = ExperimentConfig.model_validate(
            {
                "source_backtest_id": "source",
                "selection_horizon": 1,
                "split": {"embargo_bars": 1},
                "candidates": [
                    {"id": "baseline-v1", "family": "baseline"},
                    {"id": "candidate-a", "family": "weights"},
                    {"id": "candidate-b", "family": "thresholds"},
                ],
            }
        )
        positive = {"validation": {"net_median": 0.01, "signal_count": 100}}
        manifest = ExperimentManifest(
            id=experiment_id,
            status=BacktestStatus.COMPLETED,
            config=config,
            dataset_version="synthetic-v1",
            code_version="test",
            candidate_count=3,
            total_trials=3,
            search_space={},
            results=[
                CandidateResult(candidate_id="baseline-v1", family="baseline", eligible=False),
                CandidateResult(
                    candidate_id="candidate-a",
                    family="weights",
                    rank=1,
                    eligible=True,
                    selected=True,
                    metrics=positive,
                    oos_metrics={"net_median": 0.009},
                    final_test_metrics={"net_median": 0.008},
                    adjusted_p_value=0.05,
                ),
                CandidateResult(
                    candidate_id="candidate-b",
                    family="thresholds",
                    rank=2,
                    eligible=True,
                    selected=True,
                    metrics=positive,
                    oos_metrics={"net_median": 0.009},
                    final_test_metrics={"net_median": 0.008},
                    adjusted_p_value=0.05,
                ),
            ],
        )
        await repository.save_manifest(manifest)
        await repository.save_profile(profile("baseline-v1", ProfileStatus.PRODUCTION))
        await repository.save_profile(
            profile("candidate-a", ProfileStatus.CANDIDATE, experiment_id)
        )
        await repository.save_profile(
            profile("candidate-b", ProfileStatus.CANDIDATE, experiment_id)
        )
        original_hash = (await repository.get_profile("candidate-a")).content_hash  # type: ignore[union-attr]
        manager = ExperimentManager(repository, BacktestRepository(database))
        application = FastAPI()
        application.state.experiment_manager = manager
        request = Request({"type": "http", "app": application, "headers": []})

        with pytest.raises(HTTPException) as refused:
            await promote(
                "baseline-v1",
                PromotionRequest(
                    experiment_id=experiment_id, comment="refus contrôlé", confirm=True
                ),
                request,
            )
        assert refused.value.status_code == 409

        accepted = await promote(
            "candidate-a",
            PromotionRequest(
                experiment_id=experiment_id, comment="promotion contrôlée", confirm=True
            ),
            request,
        )
        assert accepted["approved"] is True
        await promote(
            "candidate-b",
            PromotionRequest(experiment_id=experiment_id, comment="seconde version", confirm=True),
            request,
        )
        rollback = await promote(
            "candidate-a",
            PromotionRequest(
                experiment_id=experiment_id, comment="rollback explicite", confirm=True
            ),
            request,
        )
        assert rollback["previous_profile_id"] == "candidate-b"
        restored_profile = await repository.get_profile("candidate-a")
        assert restored_profile is not None
        assert restored_profile.status == ProfileStatus.PRODUCTION
        assert restored_profile.content_hash == original_hash
        lifecycle = await repository.lifecycle("candidate-a")
        assert [item["to_status"] for item in lifecycle] == [
            "candidate",
            "production",
            "retired",
            "production",
        ]

        comparison = ShadowComparison(
            symbol="BTC/USDC",
            timeframe="4h",
            timestamp=datetime.now(timezone.utc),
            production_profile_id="candidate-a",
            candidate_profile_id="candidate-b",
            production={"score": 60},
            candidate={"score": 65},
            divergence_reasons=["score"],
        )
        await repository.add_shadow(comparison)
        items, total = await repository.shadows(symbol="BTC/USDC")
        assert total == 1
        assert items[0].snapshot_status == "confirmed"
        await database.close()


@pytest.mark.asyncio
async def test_automatic_shadow_is_idempotent_on_a_closed_candle() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "shadow.sqlite3")
        await database.initialize()
        repository = ExperimentRepository(database)
        scan_config = ScanConfig(
            timeframe="1m",
            min_ohlcv_bars=60,
            use_ma=False,
            ma_timeframes=[],
            min_trend_score=0,
            use_macd=False,
            use_bollinger=False,
            use_stochastic=False,
            min_confluence_score=0,
        )
        for identifier, status, threshold in (
            ("production", ProfileStatus.PRODUCTION, 35),
            ("challenger", ProfileStatus.SHADOW, 45),
        ):
            await repository.save_profile(
                SignalProfileVersion(
                    id=identifier,
                    name=identifier,
                    version="1.0.0",
                    description="shadow automatique",
                    signal_config=scan_config.model_copy(update={"rsi_threshold": threshold}),
                    dataset_version="synthetic-v1",
                    code_version="test",
                    status=status,
                )
            )
        service = ShadowEvaluationService(repository)
        window = candles()[31:91]
        assert (
            await service.evaluate_closed_candle(symbol="SYN/USDC", timeframe="1m", candles=window)
            == 1
        )
        assert (
            await service.evaluate_closed_candle(symbol="SYN/USDC", timeframe="1m", candles=window)
            == 1
        )
        comparisons, total = await repository.shadows()
        assert total == 1
        assert comparisons[0].production_profile_id == "production"
        assert comparisons[0].candidate_profile_id == "challenger"
        await database.close()
