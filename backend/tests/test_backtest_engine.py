from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.database.connection import Database
from app.models.backtest import BacktestConfig, BacktestJob, BacktestStatus
from app.repositories.backtest_repository import BacktestRepository
from app.services.backtest_engine import BacktestEngine
from app.services.portfolio_replay import PortfolioReplayError
from tests.fixtures.synthetic_backtest_v1 import candles
from tests.test_backtesting_domain import signal_config


class MemoryHistory:
    def __init__(self, rows):
        self.rows = rows

    async def before(self, symbol, timeframe, before_ms, limit, job):
        return [item for item in self.rows if item.open_time < before_ms][-limit:]

    async def range(self, symbol, timeframe, start_ms, end_ms, job):
        return [item for item in self.rows if start_ms <= item.open_time < end_ms]


class CountingMemoryHistory(MemoryHistory):
    def __init__(self, rows):
        super().__init__(rows)
        self.before_calls = 0
        self.range_calls = 0

    async def before(self, symbol, timeframe, before_ms, limit, job):
        self.before_calls += 1
        return await super().before(symbol, timeframe, before_ms, limit, job)

    async def range(self, symbol, timeframe, start_ms, end_ms, job):
        self.range_calls += 1
        return await super().range(symbol, timeframe, start_ms, end_ms, job)


@pytest.mark.asyncio
async def test_full_synthetic_replay_persists_and_survives_restart() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "backtest.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[100].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1, 3, 6],
        )
        job = BacktestJob(id="golden-v1", config=config)
        await repository.save_job(job)
        await BacktestEngine(MemoryHistory(rows), repository, yield_every=2).run(job)
        await repository.save_job(job)
        restored = await BacktestRepository(database).get_job(job.id)
        observations = await repository.all_observations(job.id)
        outcomes = await repository.all_outcomes(job.id)
        assert restored is not None and restored.summary is not None
        assert restored.summary.observation_count == 20
        assert len(observations) == 20
        assert len(outcomes) == 60
        assert all(item.snapshot_status == "confirmed" for item in observations)

        assert restored.algorithm_version == "signal-evaluation-v3"
        assert restored.checkpoint is not None
        assert restored.checkpoint["algorithm_version"] == "signal-evaluation-v3"
        assert all(
            item.algorithm_version == "signal-evaluation-v3"
            for item in observations
        )

        assert not restored.summary.trade_simulation_included
        await database.close()


@pytest.mark.asyncio
async def test_replay_persists_indicator_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Les événements de la bougie courante survivent à la persistance SQLite."""
    rows = candles()
    calls = 0

    def fake_build_indicator_events(
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1

        assert kwargs["only_last"] is True

        return [
            {
                "indicator": "rsi",
                "position": len(kwargs["rsi_series"]) - 1,
                "direction": "bullish",
                "event": "exit_oversold",
                "kind": "threshold_exit",
                "strength": 0.8,
                "metadata": {
                    "previous_rsi": 29.0,
                    "current_rsi": 31.0,
                },
            }
        ]

    monkeypatch.setattr(
        "app.domain.backtesting.build_indicator_events",
        fake_build_indicator_events,
    )

    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "indicator-events.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)

        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(
                rows[80].open_time / 1_000,
                tz=timezone.utc,
            ),
            end=datetime.fromtimestamp(
                rows[83].open_time / 1_000,
                tz=timezone.utc,
            ),
            signal_config=signal_config(),
            horizons=[1],
            replay_mode="every_bar",
        )

        job = BacktestJob(
            id="indicator-events",
            config=config,
        )
        await repository.save_job(job)

        await BacktestEngine(
            MemoryHistory(rows),
            repository,
        ).run(job)

        observations = await BacktestRepository(database).all_observations(job.id)

        assert calls == 3
        assert len(observations) == 3

        for observation in observations:
            assert len(observation.indicator_events) == 1

            event = observation.indicator_events[0]

            assert event.indicator == "rsi"
            assert event.position >= 0
            assert event.direction == "bullish"
            assert event.event == "exit_oversold"
            assert event.kind == "threshold_exit"
            assert event.strength == pytest.approx(0.8)
            assert event.metadata == {
                "previous_rsi": 29.0,
                "current_rsi": 31.0,
            }

        await database.close()


@pytest.mark.asyncio
async def test_replay_passes_primary_ema_and_macd_to_event_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le replay transmet au bundle les séries EMA et MACD du timeframe principal."""
    from app.domain.indicator_bundle import (
        build_indicator_events as real_build_indicator_events,
    )
    from app.domain.indicators import calculate_ema, calculate_macd

    rows = candles()
    calls = 0

    def spy_build_indicator_events(**kwargs: Any) -> Any:
        nonlocal calls
        calls += 1

        assert kwargs["only_last"] is True

        close_series = kwargs["close_series"]
        ema_fast = kwargs["ema_fast"]
        ema_slow = kwargs["ema_slow"]
        macd_data = kwargs["macd_data"]

        assert close_series is not None
        assert ema_fast is not None
        assert ema_slow is not None
        assert macd_data is not None

        expected_ema_fast = calculate_ema(
            close_series,
            5,
        )
        expected_ema_slow = calculate_ema(
            close_series,
            10,
        )
        expected_macd = calculate_macd(
            close_series,
            fast_period=3,
            slow_period=6,
            signal_period=2,
        )

        assert ema_fast.equals(expected_ema_fast)
        assert ema_slow.equals(expected_ema_slow)

        assert macd_data["macd"].equals(expected_macd["macd"])
        assert macd_data["signal"].equals(expected_macd["signal"])
        assert macd_data["histogram"].equals(expected_macd["histogram"])

        return real_build_indicator_events(**kwargs)

    monkeypatch.setattr(
        "app.domain.backtesting.build_indicator_events",
        spy_build_indicator_events,
    )

    base_signal_config = signal_config()
    configured_signal = base_signal_config.model_copy(
        update={
            "use_ma": True,
            "use_sma": False,
            "use_ema": True,
            "ema_periods": [5, 10],
            "ma_timeframes": [base_signal_config.timeframe],
            "use_macd": True,
            "macd_fast_period": 3,
            "macd_slow_period": 6,
            "macd_signal_period": 2,
        }
    )

    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "ema-macd-events.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)

        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(
                rows[80].open_time / 1_000,
                tz=timezone.utc,
            ),
            end=datetime.fromtimestamp(
                rows[83].open_time / 1_000,
                tz=timezone.utc,
            ),
            signal_config=configured_signal,
            horizons=[1],
            replay_mode="every_bar",
        )

        job = BacktestJob(
            id="ema-macd-events",
            config=config,
        )
        await repository.save_job(job)

        await BacktestEngine(
            MemoryHistory(rows),
            repository,
        ).run(job)

        assert calls == 3

        await database.close()


@pytest.mark.asyncio
async def test_gap_policy_rejects_range() -> None:
    rows = candles()
    rows.pop(90)
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "gap.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[79].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[99].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1],
            gap_policy="reject_range",
        )
        job = BacktestJob(id="gap", config=config)
        with pytest.raises(ValueError, match="discontinue"):
            await BacktestEngine(MemoryHistory(rows), repository).run(job)
        await database.close()


@pytest.mark.asyncio
async def test_checkpoint_resume_is_idempotent() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "resume.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[100].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1, 3],
        )
        job = BacktestJob(id="resume-v1", config=config)
        await repository.save_job(job)

        async def interrupt(progress) -> None:
            if progress.processed >= 5:
                raise RuntimeError("controlled interruption")

        engine = BacktestEngine(MemoryHistory(rows), repository, yield_every=1)
        with pytest.raises(RuntimeError, match="controlled"):
            await engine.run(job, interrupt)
        checkpoint = await repository.get_checkpoint(job.id)
        assert checkpoint is not None and checkpoint["processed"] == 5
        job.status = BacktestStatus.INTERRUPTED
        await repository.save_job(job)

        restored = await repository.get_job(job.id)
        assert restored is not None
        await engine.run(restored)
        observations = await repository.all_observations(job.id)
        outcomes = await repository.all_outcomes(job.id)
        assert restored.progress.processed == 20
        assert len(observations) == 20
        assert len(outcomes) == 40
        assert len({item.id for item in observations}) == 20
        await database.close()


@pytest.mark.asyncio
async def test_portfolio_replay_is_additive_and_resume_is_deterministic() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-resume.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[100].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1, 3],
            portfolio_simulation={
                "quote_asset": "USDC",
                "initial_capital": "10000",
                "fee_rate": "0.001",
            },
        )
        uninterrupted = BacktestJob(id="portfolio-full", config=config)
        await repository.save_job(uninterrupted)
        engine = BacktestEngine(MemoryHistory(rows), repository, yield_every=1)
        await engine.run(uninterrupted)
        full_result = await engine.portfolios.load_portfolio_simulation_result(uninterrupted.id)
        full_outcomes = await repository.all_outcomes(uninterrupted.id)
        assert full_result is not None
        assert uninterrupted.portfolio_result is None
        assert uninterrupted.summary is not None
        assert uninterrupted.summary.trade_simulation_included
        assert uninterrupted.summary.portfolio_simulation is not None
        assert uninterrupted.summary.portfolio_simulation.summary.open_position_count == 0

        resumed = BacktestJob(id="portfolio-resumed", config=config)
        await repository.save_job(resumed)

        async def interrupt(progress) -> None:
            if progress.processed >= 5:
                raise RuntimeError("controlled portfolio interruption")

        with pytest.raises(RuntimeError, match="controlled portfolio interruption"):
            await engine.run(resumed, interrupt)
        resumed.status = BacktestStatus.INTERRUPTED
        await repository.save_job(resumed)
        restored = await repository.get_job(resumed.id)
        assert restored is not None
        await engine.run(restored)
        resumed_result = await engine.portfolios.load_portfolio_simulation_result(restored.id)
        resumed_outcomes = await repository.all_outcomes(restored.id)
        assert resumed_result is not None
        assert restored.portfolio_result is None
        assert resumed_result.metrics == full_result.metrics
        assert [item.id for item in resumed_result.orders] == [
            item.id for item in full_result.orders
        ]
        assert [item.id for item in resumed_result.executions] == [
            item.id for item in full_result.executions
        ]
        assert [item.id for item in resumed_result.trades] == [
            item.id for item in full_result.trades
        ]
        assert [item.model_dump(exclude={"observation_id"}) for item in resumed_outcomes] == [
            item.model_dump(exclude={"observation_id"}) for item in full_outcomes
        ]
        assert restored.config_fingerprint == uninterrupted.config_fingerprint
        assert restored.checkpoint is not None
        assert restored.checkpoint["config_fingerprint"] == restored.config_fingerprint
        checkpoint_result = resumed_result
        await engine.run(restored)
        assert (
            await engine.portfolios.load_portfolio_simulation_result(restored.id)
            == checkpoint_result
        )
        await database.close()


@pytest.mark.asyncio
async def test_portfolio_does_not_add_historical_data_loads() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-loads.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        common = {
            "symbols": ["SYN/USDC"],
            "start": datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            "end": datetime.fromtimestamp(rows[85].open_time / 1_000, tz=timezone.utc),
            "signal_config": signal_config(),
            "horizons": [1],
        }
        legacy_history = CountingMemoryHistory(rows)
        legacy = BacktestJob(id="legacy-loads", config=BacktestConfig(**common))
        await repository.save_job(legacy)
        await BacktestEngine(legacy_history, repository).run(legacy)

        portfolio_history = CountingMemoryHistory(rows)
        portfolio = BacktestJob(
            id="portfolio-loads",
            config=BacktestConfig(
                **common,
                portfolio_simulation={"quote_asset": "USDC"},
            ),
        )
        await repository.save_job(portfolio)
        await BacktestEngine(portfolio_history, repository).run(portfolio)
        assert (portfolio_history.before_calls, portfolio_history.range_calls) == (
            legacy_history.before_calls,
            legacy_history.range_calls,
        )
        await database.close()


@pytest.mark.asyncio
async def test_requested_portfolio_fails_explicitly_on_primary_gap() -> None:
    rows = candles()
    start = rows[80].open_time
    end = rows[100].open_time
    rows.pop(90)
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-gap.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(start / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(end / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1],
            gap_policy="allow_with_warning",
            portfolio_simulation={"quote_asset": "USDC"},
        )
        job = BacktestJob(id="portfolio-gap", config=config)
        await repository.save_job(job)
        with pytest.raises(PortfolioReplayError) as raised:
            await BacktestEngine(MemoryHistory(rows), repository).run(job)
        assert raised.value.code == "portfolio_time_gap"
        assert job.summary is None
        assert job.portfolio_result is None
        await database.close()
