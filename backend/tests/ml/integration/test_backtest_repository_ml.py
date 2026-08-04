from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import pytest

from app.database.connection import Database
from app.models.backtest import (
    BacktestConfig,
    BacktestJob,
    ForwardOutcome,
    SignalObservation,
)
from app.repositories.backtest_repository import BacktestRepository

JOB_ID = "ml-repository-test"
BASE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def observation(
    *,
    symbol: str,
    decision_time: datetime,
    snapshot_status: Literal[
        "confirmed",
        "provisional",
    ] = "confirmed",
) -> SignalObservation:
    """Construit une observation minimale persistable."""
    return SignalObservation(
        job_id=JOB_ID,
        symbol=symbol,
        timeframe="1h",
        decision_time=decision_time,
        snapshot_status=snapshot_status,
        accepted=True,
        close=100.0,
        algorithm_version="signal-evaluation-v3",
        dataset_version="repository-test-v1",
    )


def outcome(
    *,
    observation_id: int,
    decision_time: datetime,
    horizon: int,
    gross_return: float,
) -> ForwardOutcome:
    """Construit un outcome identifiable pour un horizon donné."""
    return ForwardOutcome(
        observation_id=observation_id,
        horizon=horizon,
        entry_policy="signal_close",
        entry_time=decision_time,
        entry_price=100.0,
        exit_time=decision_time + timedelta(hours=horizon),
        exit_price=100.0 * (1 + gross_return),
        gross_return=gross_return,
        censored=False,
        available_bars=horizon,
        valid=True,
    )


@pytest.mark.asyncio
async def test_ml_source_rows_filters_joins_orders_and_paginates() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "ml-source-rows.sqlite3")
        await database.initialize()

        try:
            repository = BacktestRepository(database)

            job = BacktestJob(
                id=JOB_ID,
                config=BacktestConfig(
                    symbols=[
                        "BTC/USDC",
                        "ETH/USDC",
                        "SOL/USDC",
                        "XRP/USDC",
                    ],
                    start=BASE_TIME - timedelta(hours=2),
                    end=BASE_TIME + timedelta(hours=24),
                    horizons=[3, 6],
                ),
            )
            await repository.save_job(job)

            late_time = BASE_TIME + timedelta(hours=2)
            shared_time = BASE_TIME + timedelta(hours=1)
            provisional_time = BASE_TIME

            late_id = await repository.add_observation(
                observation(
                    symbol="ETH/USDC",
                    decision_time=late_time,
                )
            )
            first_id = await repository.add_observation(
                observation(
                    symbol="BTC/USDC",
                    decision_time=shared_time,
                )
            )
            second_id = await repository.add_observation(
                observation(
                    symbol="SOL/USDC",
                    decision_time=shared_time,
                )
            )
            provisional_id = await repository.add_observation(
                observation(
                    symbol="XRP/USDC",
                    decision_time=provisional_time,
                    snapshot_status="provisional",
                )
            )

            assert late_id > 0
            assert first_id > 0
            assert second_id > first_id
            assert provisional_id > 0

            await repository.add_outcomes(
                JOB_ID,
                late_id,
                [
                    outcome(
                        observation_id=late_id,
                        decision_time=late_time,
                        horizon=3,
                        gross_return=0.03,
                    ),
                    outcome(
                        observation_id=late_id,
                        decision_time=late_time,
                        horizon=6,
                        gross_return=0.06,
                    ),
                ],
            )
            await repository.add_outcomes(
                JOB_ID,
                first_id,
                [
                    outcome(
                        observation_id=first_id,
                        decision_time=shared_time,
                        horizon=6,
                        gross_return=0.01,
                    ),
                ],
            )
            await repository.add_outcomes(
                JOB_ID,
                second_id,
                [
                    outcome(
                        observation_id=second_id,
                        decision_time=shared_time,
                        horizon=6,
                        gross_return=0.02,
                    ),
                ],
            )
            await repository.add_outcomes(
                JOB_ID,
                provisional_id,
                [
                    outcome(
                        observation_id=provisional_id,
                        decision_time=provisional_time,
                        horizon=6,
                        gross_return=0.99,
                    ),
                ],
            )

            rows, total = await repository.ml_source_rows(
                JOB_ID,
                horizon=6,
                limit=10,
            )

            assert total == 3
            assert len(rows) == 3

            observations = [source_observation for source_observation, _ in rows]
            outcomes = [source_outcome for _, source_outcome in rows]

            assert [item.id for item in observations] == [
                first_id,
                second_id,
                late_id,
            ]
            assert [item.decision_time for item in observations] == [
                shared_time,
                shared_time,
                late_time,
            ]

            assert [item.observation_id for item in outcomes] == [
                first_id,
                second_id,
                late_id,
            ]
            assert all(item.horizon == 6 for item in outcomes)
            assert [item.gross_return for item in outcomes] == pytest.approx(
                [
                    0.01,
                    0.02,
                    0.06,
                ]
            )

            assert provisional_id not in {item.id for item in observations}

            page, page_total = await repository.ml_source_rows(
                JOB_ID,
                horizon=6,
                offset=1,
                limit=1,
            )

            assert page_total == 3
            assert len(page) == 1
            assert page[0][0].id == second_id
            assert page[0][1].observation_id == second_id
        finally:
            await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        (
            {
                "horizon": 0,
            },
            "horizon",
        ),
        (
            {
                "offset": -1,
            },
            "offset",
        ),
        (
            {
                "limit": 0,
            },
            "limit",
        ),
    ],
)
async def test_ml_source_rows_rejects_invalid_pagination(
    parameters: dict[str, int],
    message: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "ml-invalid-arguments.sqlite3")
        repository = BacktestRepository(database)

        with pytest.raises(
            ValueError,
            match=message,
        ):
            await repository.ml_source_rows(
                JOB_ID,
                **parameters,
            )
