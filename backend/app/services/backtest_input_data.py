"""Chargement unique des séries réellement fournies au moteur de backtest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.candles import Candle, timeframe_milliseconds
from app.domain.limits import ma_ohlcv_limit, primary_ohlcv_limit
from app.domain.ohlcv_fingerprint import (
    BacktestInputFingerprint,
    InputDataStreamFingerprint,
    aggregate_input_fingerprints,
    fingerprint_ohlcv_stream,
)
from app.models.backtest import BacktestJob


class HistoricalRepository(Protocol):
    async def before(
        self, symbol: str, timeframe: str, before_ms: int, limit: int, job: BacktestJob
    ) -> list[Candle]: ...

    async def range(
        self, symbol: str, timeframe: str, start_ms: int, end_ms: int, job: BacktestJob
    ) -> list[Candle]: ...


@dataclass(slots=True)
class LoadedSeries:
    candles: list[Candle]
    first_decision_index: int
    last_decision_index: int
    gap_after: set[int]


@dataclass(slots=True)
class BacktestInputSnapshot:
    primary: dict[str, LoadedSeries]
    trends: dict[str, dict[str, list[Candle]]]
    stream_fingerprints: tuple[InputDataStreamFingerprint, ...]

    def fingerprint(self, source_identity: str) -> BacktestInputFingerprint:
        return aggregate_input_fingerprints(source_identity, self.stream_fingerprints)


async def _load_primary(
    history: HistoricalRepository, job: BacktestJob, symbol: str
) -> tuple[LoadedSeries, InputDataStreamFingerprint]:
    config = job.config
    signal = config.signal_config
    start_ms = int(config.start.timestamp() * 1_000)
    end_ms = int(config.end.timestamp() * 1_000)
    interval = timeframe_milliseconds(signal.timeframe)
    warmup = primary_ohlcv_limit(signal)
    future = max(config.horizons) + int(config.entry_policy == "next_open") + 1
    before = await history.before(symbol, signal.timeframe, start_ms, warmup, job)
    requested_end = end_ms + future * interval
    after = await history.range(symbol, signal.timeframe, start_ms, requested_end, job)
    candles = [*before, *after]
    decision_indices = [
        index for index, candle in enumerate(candles) if start_ms <= candle.open_time < end_ms
    ]
    if not decision_indices:
        raise ValueError(f"Aucune bougie fermée pour {symbol} sur la plage")
    gaps = {
        index
        for index in range(len(candles) - 1)
        if candles[index + 1].open_time - candles[index].open_time != interval
    }
    range_gaps = {
        index for index in gaps if decision_indices[0] - 1 <= index < decision_indices[-1]
    }
    if range_gaps and config.gap_policy == "reject_range":
        raise ValueError(f"Couverture discontinue pour {symbol}: {len(range_gaps)} trou(s)")
    if range_gaps:
        job.warnings.append(f"{symbol}: {len(range_gaps)} trou(s), politique {config.gap_policy}")
    loaded = LoadedSeries(candles, decision_indices[0], decision_indices[-1], gaps)
    stream = fingerprint_ohlcv_stream(
        candles,
        role="primary",
        exchange_id=signal.exchange_id,
        market_type=signal.market_type,
        symbol=symbol,
        timeframe=signal.timeframe,
        requested_start_ms=start_ms - warmup * interval,
        requested_end_ms=requested_end,
        closed_only=True,
        warmup_bars=warmup,
        future_bars=future,
        gaps_validated=not gaps,
    )
    return loaded, stream


async def _load_trends(
    history: HistoricalRepository,
    job: BacktestJob,
    symbol: str,
    end_ms: int,
) -> tuple[dict[str, list[Candle]], list[InputDataStreamFingerprint]]:
    signal = job.config.signal_config
    if not signal.use_ma:
        return {}, []
    start_ms = int(job.config.start.timestamp() * 1_000)
    warmup = ma_ohlcv_limit(signal)
    result: dict[str, list[Candle]] = {}
    streams: list[InputDataStreamFingerprint] = []
    for timeframe in signal.ma_timeframes:
        if timeframe == signal.timeframe:
            continue
        before = await history.before(symbol, timeframe, start_ms, warmup, job)
        current = await history.range(symbol, timeframe, start_ms, end_ms, job)
        candles = [*before, *current]
        interval = timeframe_milliseconds(timeframe)
        gaps = any(
            right.open_time - left.open_time != interval
            for left, right in zip(candles, candles[1:])
        )
        result[timeframe] = candles
        streams.append(
            fingerprint_ohlcv_stream(
                candles,
                role=f"trend:{timeframe}",
                exchange_id=signal.exchange_id,
                market_type=signal.market_type,
                symbol=symbol,
                timeframe=timeframe,
                requested_start_ms=start_ms - warmup * interval,
                requested_end_ms=end_ms,
                closed_only=True,
                warmup_bars=warmup,
                future_bars=0,
                gaps_validated=not gaps,
            )
        )
    return result, streams


async def load_backtest_input_snapshot(
    history: HistoricalRepository, job: BacktestJob
) -> BacktestInputSnapshot:
    """Charge une fois chaque flux et calcule ses métadonnées fortes en O(n)."""
    primary: dict[str, LoadedSeries] = {}
    trends: dict[str, dict[str, list[Candle]]] = {}
    streams: list[InputDataStreamFingerprint] = []
    for symbol in job.config.symbols:
        loaded, stream = await _load_primary(history, job, symbol)
        primary[symbol] = loaded
        streams.append(stream)
        end_with_future = loaded.candles[-1].close_time or loaded.candles[-1].open_time
        symbol_trends, trend_streams = await _load_trends(history, job, symbol, end_with_future)
        trends[symbol] = symbol_trends
        streams.extend(trend_streams)
    return BacktestInputSnapshot(primary, trends, tuple(streams))
