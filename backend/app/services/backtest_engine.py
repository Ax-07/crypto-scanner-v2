"""Rejeu historique causal sur le dépôt OHLCV local, sans accès réseau."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable

from app.domain.backtesting import (
    build_analytics,
    calculate_forward_outcomes,
)
from app.domain.signal_evaluation import evaluate_signal_snapshot
from app.domain.candles import Candle, timeframe_milliseconds
from app.domain.limits import ma_ohlcv_limit, primary_ohlcv_limit
from app.domain.portfolio import simulate_portfolio
from app.models.backtest import (
    SIGNAL_EVALUATION_VERSION,
    BacktestJob,
    BacktestProgress,
    BacktestSummary,
)
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.services.backtest_input_data import (
    HistoricalRepository,
    load_backtest_input_snapshot,
)
from app.services.portfolio_replay import (
    backtest_config_fingerprint,
    build_portfolio_simulation_steps,
    to_internal_portfolio_config,
    to_public_portfolio_result,
)

ProgressCallback = Callable[[BacktestProgress], Awaitable[None]]


class SQLiteHistoricalRepository:
    """Adaptateur de lecture uniquement au-dessus de la base de production."""

    def __init__(self, candles: CandleRepository) -> None:
        self.candles = candles

    async def before(
        self, symbol: str, timeframe: str, before_ms: int, limit: int, job: BacktestJob
    ) -> list[Candle]:
        signal = job.config.signal_config
        return await self.candles.get_candles_before(
            exchange_id=signal.exchange_id,
            market_type=signal.market_type,
            symbol=symbol,
            timeframe=timeframe,
            before_open_time=before_ms,
            limit=limit,
            closed_only=True,
        )

    async def range(
        self, symbol: str, timeframe: str, start_ms: int, end_ms: int, job: BacktestJob
    ) -> list[Candle]:
        signal = job.config.signal_config
        return await self.candles.get_range(
            signal.exchange_id,
            signal.market_type,
            symbol,
            timeframe,
            from_time=start_ms,
            to_time=end_ms,
            limit=2_000_000,
            closed_only=True,
        )


class BacktestEngine:
    def __init__(
        self,
        history: HistoricalRepository,
        results: BacktestRepository,
        *,
        yield_every: int = 25,
        portfolios: PortfolioRepository | None = None,
    ) -> None:
        self.history = history
        self.results = results
        self.portfolios = portfolios or PortfolioRepository(results.database)
        self.yield_every = yield_every

    async def run(self, job: BacktestJob, on_progress: ProgressCallback | None = None) -> None:
        config = job.config
        if config.snapshot_status == "provisional":
            raise ValueError(
                "Les OHLCV historiques ne conservent pas les révisions intrabar; "
                "un rejeu provisional causal est indisponible."
            )
        expected_input = await self.results.get_ml_v2_source_input(job.id)
        input_snapshot = await load_backtest_input_snapshot(self.history, job)
        loaded = input_snapshot.primary
        input_data_fingerprint: str | None = None
        if expected_input is not None:
            actual_input = input_snapshot.fingerprint(expected_input.fingerprint.source_identity)
            if actual_input != expected_input.fingerprint:
                raise ValueError(
                    "Les données OHLCV chargées par le moteur diffèrent du fingerprint "
                    "prévalidé; le source doit être recréé."
                )
            await self.results.confirm_ml_v2_source_input(
                job.id, actual_input.input_data_fingerprint
            )
            input_data_fingerprint = actual_input.input_data_fingerprint
        fingerprint_payload = "|".join(
            f"{symbol}:{series.candles[0].open_time}:{series.candles[-1].open_time}:"
            f"{len(series.candles)}"
            for symbol, series in sorted(loaded.items())
        )
        job.dataset_version = "sha256:" + hashlib.sha256(fingerprint_payload.encode()).hexdigest()
        config_fingerprint = (
            backtest_config_fingerprint(config) if config.portfolio_simulation is not None else None
        )
        job.config_fingerprint = config_fingerprint
        checkpoint = await self.results.get_checkpoint(job.id)

        if checkpoint is not None:
            checkpoint_algorithm_version = str(
                checkpoint.get(
                    "algorithm_version",
                    "signal-evaluation-v2",
                )
            )

            if checkpoint_algorithm_version != SIGNAL_EVALUATION_VERSION:
                raise ValueError(
                    "Checkpoint incompatible avec la version actuelle du moteur : "
                    f"{checkpoint_algorithm_version} != {SIGNAL_EVALUATION_VERSION}. "
                    "Créez un nouveau backtest au lieu de reprendre cet ancien job."
                )

        job.algorithm_version = SIGNAL_EVALUATION_VERSION

        resume_symbol_index = int(checkpoint.get("symbol_index", 0)) if checkpoint else 0
        resume_decision_index = int(checkpoint.get("decision_index", -1)) if checkpoint else -1
        if checkpoint:
            job.progress.processed = int(checkpoint.get("processed", 0))
            job.progress.observations = int(checkpoint.get("observations", 0))
            job.checkpoint = checkpoint
        job.progress.total = sum(
            item.last_decision_index - item.first_decision_index + 1 for item in loaded.values()
        )
        job.progress.phase = "replay"
        if on_progress:
            await on_progress(job.progress.model_copy(deep=True))

        last_state: dict[str, list[object]] = dict(
            checkpoint.get("last_state", {}) if checkpoint else {}
        )
        for symbol_index, symbol in enumerate(config.symbols):
            if symbol_index < resume_symbol_index:
                continue
            job.progress.current_symbol = symbol
            series = loaded[symbol]
            higher = input_snapshot.trends[symbol]
            signal = config.signal_config
            primary_limit = primary_ohlcv_limit(signal)
            trend_limit = ma_ohlcv_limit(signal)
            for index in range(series.first_decision_index, series.last_decision_index + 1):
                if symbol_index == resume_symbol_index and index <= resume_decision_index:
                    continue
                candle = series.candles[index]
                decision_ms = candle.close_time or (
                    candle.open_time + timeframe_milliseconds(signal.timeframe)
                )
                primary_start = max(0, index - primary_limit + 1)
                window_gap = any(
                    gap_index in series.gap_after for gap_index in range(primary_start, index)
                )
                if window_gap and config.gap_policy == "skip_affected":
                    job.progress.processed += 1
                    continue
                primary = series.candles[primary_start : index + 1]
                trend_sets: dict[str, list[Candle]] = {signal.timeframe: primary}
                for timeframe, candles in higher.items():
                    eligible = [
                        item
                        for item in candles
                        if (item.close_time or item.open_time) <= decision_ms
                    ]
                    trend_sets[timeframe] = eligible[-trend_limit:]
                observation = evaluate_signal_snapshot(
                    job_id=job.id,
                    symbol=symbol,
                    decision_time_ms=decision_ms,
                    primary=primary,
                    trend_candles=trend_sets,
                    profile=signal,
                    snapshot_status=config.snapshot_status,
                    dataset_version=job.dataset_version,
                    profile_id=config.signal_profile_id,
                )

                signature: list[object] = [
                    observation.accepted,
                    observation.rejection_stage,
                    observation.confluence_grade,
                    observation.macd_signal,
                    observation.bollinger_position,
                    observation.stochastic_signal,
                    [list(item) for item in sorted(observation.trend_states.items())],
                ]
                keep = (
                    config.replay_mode == "every_bar"
                    or (config.replay_mode == "filtered_signals" and observation.accepted)
                    or (
                        config.replay_mode == "state_changes"
                        and last_state.get(symbol) != signature
                    )
                )
                last_state[symbol] = signature
                if keep:
                    observation_id = await self.results.add_observation(observation)
                    observation.id = observation_id
                    outcomes = calculate_forward_outcomes(
                        observation_id,
                        series.candles,
                        index,
                        config,
                        blocked_intervals=(
                            {item + 1 for item in series.gap_after}
                            if config.gap_policy == "skip_affected"
                            else set()
                        ),
                    )
                    await self.results.add_outcomes(job.id, observation_id, outcomes)
                    job.progress.observations += 1
                job.progress.processed += 1
                if job.progress.processed % self.yield_every == 0:
                    checkpoint = {
                        "symbol_index": symbol_index,
                        "symbol": symbol,
                        "decision_index": index,
                        "processed": job.progress.processed,
                        "observations": job.progress.observations,
                        "algorithm_version": job.algorithm_version,
                        "dataset_version": job.dataset_version,
                        "status": "running",
                        "last_state": last_state,
                    }
                    if job.config_fingerprint is not None:
                        checkpoint["config_fingerprint"] = job.config_fingerprint
                    if input_data_fingerprint is not None:
                        checkpoint["input_data_fingerprint"] = input_data_fingerprint
                    job.checkpoint = checkpoint
                    await self.results.save_checkpoint(job.id, checkpoint)
                    if on_progress:
                        await on_progress(job.progress.model_copy(deep=True))
                    await asyncio.sleep(0)

        job.progress.phase = "analytics"
        if on_progress:
            await on_progress(job.progress.model_copy(deep=True))
        observations = await self.results.all_observations(job.id)
        outcomes = await self.results.all_outcomes(job.id)
        summary, correlations, ablations = build_analytics(
            observations, outcomes, config, job.warnings
        )
        if config.portfolio_simulation is not None:
            symbol = config.symbols[0]
            steps = build_portfolio_simulation_steps(
                observations=observations,
                primary_candles=loaded[symbol].candles,
                symbol=symbol,
                timeframe=config.signal_config.timeframe,
            )
            portfolio_result = simulate_portfolio(
                symbol=symbol,
                steps=steps,
                config=to_internal_portfolio_config(config.portfolio_simulation),
            )
            assert config_fingerprint is not None
            await self.portfolios.replace_simulation_result(
                job_id=job.id,
                result=portfolio_result,
                config_fingerprint=config_fingerprint,
            )
            summary["trade_simulation_included"] = True
            summary["portfolio_simulation"] = to_public_portfolio_result(
                portfolio_result
            ).model_dump(mode="json")
            job.set_portfolio_result(None)
        job.summary = BacktestSummary.model_validate(summary)
        job.correlations = correlations
        job.ablations = ablations
        for kind, payload in (
            ("summary", summary),
            ("segments", summary.get("segments", {})),
            ("funnel", summary.get("filter_funnel", [])),
            ("correlations", correlations),
            ("ablations", ablations),
            (
                "divergences",
                [
                    {"observation_id": item.id, "items": item.divergences}
                    for item in observations
                    if item.divergences
                ],
            ),
        ):
            await self.results.save_artifact(job.id, kind, payload)
        final_checkpoint = {
            "symbol_index": len(config.symbols),
            "symbol": None,
            "decision_index": -1,
            "processed": job.progress.processed,
            "observations": job.progress.observations,
            "algorithm_version": job.algorithm_version,
            "dataset_version": job.dataset_version,
            "status": "completed",
        }
        if job.config_fingerprint is not None:
            final_checkpoint["config_fingerprint"] = job.config_fingerprint
        if input_data_fingerprint is not None:
            final_checkpoint["input_data_fingerprint"] = input_data_fingerprint
        job.checkpoint = final_checkpoint
        await self.results.save_checkpoint(job.id, final_checkpoint)
        job.progress.phase = "completed"
        job.progress.current_symbol = None
