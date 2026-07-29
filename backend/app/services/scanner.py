"""Orchestre l'analyse concurrente des symboles et l'ordre des filtres.

``ScannerService`` possède l'état d'un seul scan. Il délègue l'accès CCXT aux
adaptateurs, les calculs purs au domaine et ne gère pas le cycle de vie du job.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

import pandas as pd

from app.core.settings import ScanConfig
from app.core.config import get_app_settings
from app.database.connection import Database
from app.domain.analysis import AnalysisOutcome, AnalysisStatus
from app.domain.limits import ma_ohlcv_limit, primary_ohlcv_limit
from app.domain.indicator_bundle import build_indicator_signals
from app.domain.signal_filters import (
    check_structured_signal_filters,
    include_disabled_filter_signals,
    resolve_effective_signal_filters,
)
from app.models.scanner import ScanProgress, ScanResult
from app.services.exchange import create_exchange, load_filtered_symbols
from app.domain.indicators import (
    Availability,
    ConfluenceGrade,
    TrendState,
    calculate_bollinger_bands,
    calculate_confluence_score,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
    check_signal_filters,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_stochastic_signal,
    detect_trend,
    is_bollinger_degenerate,
)
from app.services.market_data import fetch_ohlcv, get_closed_candles, get_last_closed_candle
from app.repositories.candle_repository import CandleRepository
from app.services.candle_sync import CandleSyncService

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[ScanProgress], Awaitable[None]]
"""Callback asynchrone recevant une copie cohérente de la progression."""


class ScannerService:
    """Analyse les marchés d'un ``ScanConfig`` avec une concurrence bornée.

    Une instance ne doit servir qu'à un scan. Elle conserve un cache OHLCV local
    et les résultats partiels afin qu'une annulation puisse les restituer.
    """

    def __init__(
        self,
        config: ScanConfig,
        exchange_factory=None,
        candle_sync: CandleSyncService | None = None,
    ) -> None:
        """Initialise le scanner et son sémaphore sans ouvrir de connexion."""
        self.config = config
        self.exchange_factory = exchange_factory
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self.partial_results: list[ScanResult] = []
        self._candle_cache: dict[tuple[str, str], pd.DataFrame | None] = {}
        settings = get_app_settings()
        self.candle_sync = candle_sync or CandleSyncService(
            CandleRepository(Database(settings.database_path)), settings
        )

    async def scan(self, on_progress: ProgressCallback | None = None) -> list[ScanResult]:
        """Charge les symboles, les analyse progressivement, puis trie les résultats.

        Au plus ``max_concurrency`` tâches sont simultanément planifiées. Une
        erreur de symbole reste isolée. En cas d'annulation, les tâches restantes
        sont annulées et l'exchange est toujours fermé dans ``finally``.

        Args:
            on_progress: Callback appelé au départ puis après chaque symbole.

        Returns:
            Résultats ayant franchi les filtres, triés selon la configuration.

        Raises:
            asyncio.CancelledError: Si la tâche globale du scan est annulée.
        """
        exchange = (self.exchange_factory or create_exchange)(self.config)
        pending: set[asyncio.Task[AnalysisOutcome]] = set()
        try:
            symbols = await load_filtered_symbols(exchange, self.config)
            progress = ScanProgress(total=len(symbols))
            if on_progress:
                await on_progress(progress.model_copy(deep=True))

            results = self.partial_results
            symbol_iterator = iter(symbols)

            def schedule_next() -> bool:
                """Planifie le prochain symbole sans dépasser la fenêtre de tâches."""
                try:
                    symbol = next(symbol_iterator)
                except StopIteration:
                    return False
                pending.add(asyncio.create_task(self._analyze_guarded(exchange, symbol)))
                return True

            for _ in range(min(self.config.max_concurrency, len(symbols))):
                schedule_next()

            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    outcome = await task
                    progress.processed += 1
                    if outcome.status is AnalysisStatus.SUCCESS and outcome.result is not None:
                        results.append(outcome.result)
                        progress.successful += 1
                    elif outcome.status is AnalysisStatus.FILTERED:
                        progress.filtered += 1
                    else:
                        progress.errors += 1
                    if on_progress:
                        await on_progress(progress.model_copy(deep=True))
                    schedule_next()

            self._sort_results(results)
            return results
        except asyncio.CancelledError:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            raise
        finally:
            await exchange.close()

    def _sort_results(self, results: list[ScanResult]) -> None:
        """Trie par confluence, sinon RSI, sinon tendance, avec le symbole en départage."""
        if self.config.use_confluence_score:
            results.sort(
                key=lambda item: (
                    -(item.confluence_score if item.confluence_score is not None else -1),
                    item.symbol,
                )
            )
        elif self.config.use_rsi:
            results.sort(key=lambda item: (item.rsi if item.rsi is not None else 101, item.symbol))
        elif self.config.use_ma:
            results.sort(
                key=lambda item: (
                    -(item.trend_score if item.trend_score is not None else -1),
                    item.symbol,
                )
            )
        else:
            results.sort(key=lambda item: item.symbol)

    async def _analyze_guarded(self, exchange: Any, symbol: str) -> AnalysisOutcome:
        """Exécute une analyse sous sémaphore et transforme ses erreurs en issue interne."""
        async with self._semaphore:
            try:
                outcome = await self.analyze_symbol(exchange, symbol)
                if isinstance(outcome, tuple):  # compatibility for test/client overrides
                    status, result = outcome
                    return AnalysisOutcome(AnalysisStatus(status), result=result)
                return outcome
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Analyse impossible pour %s", symbol)
                return AnalysisOutcome(AnalysisStatus.ERROR, error=str(exc))

    async def analyze_symbol(self, exchange: Any, symbol: str) -> AnalysisOutcome:
        """Exécute l'adaptateur scanner en un seul passage de calcul.

        La parité avec le moteur canonique est vérifiée par les tests de
        service. Le scanner ne recalcule donc plus tous les indicateurs en
        production uniquement pour effectuer ce contrôle.
        """
        return await self._analyze_symbol_adapter(exchange, symbol)

    async def _analyze_symbol_adapter(self, exchange: Any, symbol: str) -> AnalysisOutcome:
        """Analyse une paire en appliquant les filtres du moins au plus coûteux.

        Le RSI peut rejeter avant les timeframes MA; la tendance précède les
        indicateurs multiples, puis les filtres de signaux et la confluence.
        Seules des bougies clôturées alimentent ces calculs.
        """
        config = self.config
        required = primary_ohlcv_limit(config)
        base_frame = await self._fetch_cached(exchange, symbol, config.timeframe, required + 1)
        if base_frame is None:
            return AnalysisOutcome(AnalysisStatus.ERROR, error="Données OHLCV indisponibles")

        base_frame = get_closed_candles(base_frame, config.timeframe)
        if len(base_frame) < required:
            message = (
                "Données OHLCV insuffisantes après normalisation et clôture: "
                f"{len(base_frame)}/{required} bougies valides"
            )
            logger.warning("%s pour %s %s", message, symbol, config.timeframe)
            return AnalysisOutcome(AnalysisStatus.ERROR, error=message)

        last_candle = get_last_closed_candle(base_frame, config.timeframe)
        rsi: float | None = None
        rsi_series: pd.Series | None = None
        if config.use_rsi:
            rsi_series = calculate_rsi(base_frame["close"], config.rsi_period)
            valid_rsi = rsi_series.dropna()
            rsi = float(valid_rsi.iloc[-1]) if not valid_rsi.empty else None
            if rsi is None:
                return AnalysisOutcome(AnalysisStatus.ERROR, error="Données RSI insuffisantes")
            if rsi >= config.rsi_threshold:
                return AnalysisOutcome(AnalysisStatus.FILTERED)

        moving_averages, trends, trend_states, trend_score, trend_net_score = (
            await self._analyze_ma(
                exchange,
                symbol,
                base_frame,
            )
        )
        if config.use_ma and trend_score < config.min_trend_score:
            return AnalysisOutcome(AnalysisStatus.FILTERED)

        multi = self._analyze_multi_indicators(base_frame, rsi_series=rsi_series)
        bollinger_invalid = bool(multi.pop("_bollinger_invalid", False))
        stochastic_invalid = bool(multi.pop("_stochastic_invalid", False))
        indicator_signals = cast(
            dict[str, Any],
            multi.pop("_indicator_signals"),
        )
        structured_indicators = (
            set(config.structured_signal_filters.indicators)
            if config.structured_signal_filters is not None
            else set()
        )
        unavailable_filter = (
            (
                config.use_macd
                and "macd" not in structured_indicators
                and config.filter_macd_signal
                and multi.get("macd_signal_type") is None
            )
            or (
                config.use_bollinger
                and "bollinger" not in structured_indicators
                and config.filter_bb_position
                and multi.get("bb_position") is None
            )
            or (
                config.use_stochastic
                and "stochastic" not in structured_indicators
                and config.filter_stoch_signal
                and multi.get("stoch_signal") is None
            )
        )
        if unavailable_filter:
            return AnalysisOutcome(
                AnalysisStatus.ERROR,
                error="Indicateur requis par un filtre indisponible",
            )
        if config.structured_signal_filters is None:
            signal_filters_pass = check_signal_filters(
                macd_signal=multi.get("macd_signal_type"),
                bb_position=multi.get("bb_position"),
                stoch_signal=multi.get("stoch_signal"),
                filter_macd=config.filter_macd_signal if config.use_macd else None,
                filter_bb=config.filter_bb_position if config.use_bollinger else None,
                filter_stoch=config.filter_stoch_signal if config.use_stochastic else None,
            )
        else:
            effective_filters = resolve_effective_signal_filters(
                structured_filters=config.structured_signal_filters.model_dump(mode="python"),
                filter_macd=config.filter_macd_signal if config.use_macd else None,
                filter_bb=config.filter_bb_position if config.use_bollinger else None,
                filter_stoch=config.filter_stoch_signal if config.use_stochastic else None,
            )
            signal_filters_pass = (
                True
                if effective_filters is None
                else check_structured_signal_filters(
                    indicator_signals=include_disabled_filter_signals(
                        indicator_signals=indicator_signals,
                        disabled_indicators=[
                            name
                            for name, enabled in (
                                ("macd", config.use_macd),
                                ("bollinger", config.use_bollinger),
                                ("stochastic", config.use_stochastic),
                            )
                            if not enabled
                        ],
                    ),
                    filters=effective_filters,
                )
            )
        if not signal_filters_pass:
            return AnalysisOutcome(AnalysisStatus.FILTERED)

        confluence_score: float | None = None
        confluence_grade: ConfluenceGrade | None = None
        confluence_breakdown: dict[str, float] = {}
        confluence_effective_weights: dict[str, float] = {}
        confluence_details: dict[str, dict[str, Any]] = {}
        availability: dict[str, Availability] = {
            "rsi": (
                "available"
                if rsi is not None
                else "disabled" if not config.use_rsi else "insufficient_data"
            ),
            "trend": (
                "available"
                if config.use_ma and any(state != "unavailable" for state in trend_states.values())
                else "disabled" if not config.use_ma else "insufficient_data"
            ),
            "macd": (
                "available"
                if multi.get("macd_signal_type") is not None
                else "disabled" if not config.use_macd else "insufficient_data"
            ),
            "bollinger": (
                "available"
                if multi.get("bb_position") is not None
                else (
                    "disabled"
                    if not config.use_bollinger
                    else "invalid_data" if bollinger_invalid else "insufficient_data"
                )
            ),
            "stochastic": (
                "available"
                if multi.get("stoch_signal") is not None
                else (
                    "disabled"
                    if not config.use_stochastic
                    else "invalid_data" if stochastic_invalid else "insufficient_data"
                )
            ),
        }
        if config.use_confluence_score:
            active_weights = {
                name: weight
                for name, weight in config.confluence_weights.items()
                if (
                    (name == "rsi" and config.use_rsi)
                    or (name == "trend" and config.use_ma)
                    or (name == "macd" and config.use_macd)
                    or (name == "bollinger" and config.use_bollinger)
                    or (name == "stochastic" and config.use_stochastic)
                )
            }
            confluence = calculate_confluence_score(
                rsi_value=rsi,
                rsi_threshold=config.rsi_threshold,
                trend_score=(
                    trend_score
                    if config.use_ma and any(value is not None for value in trends.values())
                    else None
                ),
                max_trend_score=sum(value is not None for value in trends.values()),
                macd_signal=multi.get("macd_signal_type"),
                bb_position=multi.get("bb_position"),
                stoch_signal=multi.get("stoch_signal"),
                weights=active_weights,
                trend_states=list(trend_states.values()) if config.use_ma else None,
                availability=availability,
                raw_values={
                    "rsi": rsi,
                    "trend_signal": trend_states,
                    "macd_signal": multi.get("macd_signal_type"),
                    "bollinger_signal": multi.get("bb_position"),
                    "stochastic_signal": multi.get("stoch_signal"),
                },
            )
            if confluence is not None:
                confluence_score = confluence["score"]
                confluence_grade = cast(ConfluenceGrade, confluence["grade"])
                confluence_breakdown = confluence["breakdown"]
                confluence_effective_weights = confluence["effective_weights"]
                confluence_details = confluence["details"]
                if confluence_score < config.min_confluence_score:
                    return AnalysisOutcome(AnalysisStatus.FILTERED)

        result = ScanResult(
            symbol=symbol,
            timeframe=config.timeframe,
            rsi=round(rsi, 2) if rsi is not None else None,
            last_close_price=last_candle["close"] if last_candle else None,
            last_close_time=last_candle["time"] if last_candle else None,
            trend_score=trend_score if config.use_ma else None,
            trends=trends,
            trend_states=trend_states,
            trend_net_score=trend_net_score if config.use_ma else None,
            moving_averages=moving_averages,
            confluence_score=confluence_score,
            confluence_grade=confluence_grade,
            confluence_breakdown=confluence_breakdown,
            confluence_effective_weights=confluence_effective_weights,
            confluence_details=confluence_details,
            indicator_availability=availability,
            indicator_signals=indicator_signals,
            **multi,
        )
        return AnalysisOutcome(AnalysisStatus.SUCCESS, result=result)

    async def _fetch_cached(
        self, exchange: Any, symbol: str, timeframe: str, limit: int
    ) -> pd.DataFrame | None:
        """Réutilise les bougies d'un symbole/timeframe si la longueur suffit."""
        key = (symbol, timeframe)
        cached = self._candle_cache.get(key)
        if cached is not None and len(cached) >= limit - 1:
            return cached
        frame = await fetch_ohlcv(
            exchange,
            symbol,
            timeframe,
            limit,
            self.config,
            self.candle_sync,
        )
        self._candle_cache[key] = frame
        return frame

    async def _analyze_ma(
        self,
        exchange: Any,
        symbol: str,
        base_frame: pd.DataFrame,
    ) -> tuple[
        dict[str, float],
        dict[str, bool | None],
        dict[str, TrendState],
        int,
        int,
    ]:
        """Calcule les MA, le booléen de tendance et le score multi-timeframes.

        Toutes les périodes configurées sont exposées. La détection compare les
        deux plus courtes périodes disponibles de chaque famille; avec une seule,
        elle compare directement le prix. Un timeframe indisponible vaut ``None``.
        """
        config = self.config
        if not config.use_ma:
            return {}, {}, {}, 0, 0

        all_periods = ([] if not config.use_sma else config.sma_periods) + (
            [] if not config.use_ema else config.ema_periods
        )
        max_period = max(all_periods, default=0)
        ma_limit = ma_ohlcv_limit(config)
        moving_averages: dict[str, float] = {}
        trends: dict[str, bool | None] = {}
        trend_states: dict[str, TrendState] = {}
        trend_score = 0
        trend_net_score = 0

        for timeframe in config.ma_timeframes:
            if timeframe == config.timeframe and len(base_frame) >= max_period:
                frame = base_frame
            else:
                raw = await self._fetch_cached(exchange, symbol, timeframe, ma_limit + 1)
                frame = get_closed_candles(raw, timeframe) if raw is not None else None

            if frame is None or len(frame) < max_period:
                trends[timeframe] = None
                trend_states[timeframe] = "unavailable"
                continue

            sma_values: dict[int, float] = {}
            ema_values: dict[int, float] = {}
            if config.use_sma:
                for period in config.sma_periods:
                    series = calculate_sma(frame["close"], period).dropna()
                    if not series.empty:
                        value = float(series.iloc[-1])
                        sma_values[period] = value
                        moving_averages[f"sma_{period}_{timeframe}"] = round(value, 10)
            if config.use_ema:
                for period in config.ema_periods:
                    series = calculate_ema(frame["close"], period).dropna()
                    if not series.empty:
                        value = float(series.iloc[-1])
                        ema_values[period] = value
                        moving_averages[f"ema_{period}_{timeframe}"] = round(value, 10)

            sma_periods = sorted(sma_values)
            ema_periods = sorted(ema_values)
            sma_fast = sma_values.get(sma_periods[0]) if sma_periods else None
            sma_slow = sma_values.get(sma_periods[1]) if len(sma_periods) >= 2 else None
            ema_fast = ema_values.get(ema_periods[0]) if ema_periods else None
            ema_slow = ema_values.get(ema_periods[1]) if len(ema_periods) >= 2 else None

            if sma_fast is None and ema_fast is None:
                trends[timeframe] = None
                trend_states[timeframe] = "unavailable"
                continue

            state = detect_trend(frame["close"], sma_fast, sma_slow, ema_fast, ema_slow)
            trend_states[timeframe] = state
            trends[timeframe] = state == "bullish"
            trend_score += int(state == "bullish")
            trend_net_score += 1 if state == "bullish" else -1 if state == "bearish" else 0

        return moving_averages, trends, trend_states, trend_score, trend_net_score

    def _analyze_multi_indicators(
        self,
        frame: pd.DataFrame,
        *,
        rsi_series: pd.Series | None = None,
    ) -> dict[str, Any]:
        """Calcule MACD, Bollinger et Stochastique lorsqu'ils sont activés."""
        config = self.config
        result: dict[str, Any] = {}
        macd_data: dict[str, pd.Series] | None = None
        bands: dict[str, pd.Series] | None = None
        stochastic_data: dict[str, pd.Series] | None = None

        if config.use_macd:
            macd_data = calculate_macd(
                frame["close"],
                config.macd_fast_period,
                config.macd_slow_period,
                config.macd_signal_period,
            )
            valid = pd.concat(macd_data, axis=1).dropna()
            if not valid.empty:
                result.update(
                    macd=round(float(macd_data["macd"].dropna().iloc[-1]), 10),
                    macd_signal=round(float(macd_data["signal"].dropna().iloc[-1]), 10),
                    macd_histogram=round(float(macd_data["histogram"].dropna().iloc[-1]), 10),
                    macd_signal_type=detect_macd_signal(macd_data),
                )

        if config.use_bollinger:
            bands = calculate_bollinger_bands(
                frame["close"],
                config.bollinger_period,
                config.bollinger_std_dev,
            )
            valid = pd.concat(bands, axis=1).dropna()
            if not valid.empty:
                result.update(
                    bb_upper=round(float(bands["upper"].dropna().iloc[-1]), 10),
                    bb_middle=round(float(bands["middle"].dropna().iloc[-1]), 10),
                    bb_lower=round(float(bands["lower"].dropna().iloc[-1]), 10),
                )
                if is_bollinger_degenerate(frame["close"], bands):
                    result["_bollinger_invalid"] = True
                else:
                    result["bb_position"] = detect_bollinger_signal(frame["close"], bands)

        if config.use_stochastic:
            stochastic_data = calculate_stochastic(
                frame["high"],
                frame["low"],
                frame["close"],
                config.stochastic_k_period,
                config.stochastic_d_period,
            )
            valid = pd.concat(stochastic_data, axis=1).dropna()
            if not valid.empty:
                result.update(
                    stoch_k=round(float(stochastic_data["k"].dropna().iloc[-1]), 2),
                    stoch_d=round(float(stochastic_data["d"].dropna().iloc[-1]), 2),
                    stoch_signal=detect_stochastic_signal(
                        stochastic_data,
                        config.stochastic_oversold,
                        config.stochastic_overbought,
                    ),
                )
            elif len(frame) >= config.stochastic_k_period:
                result["_stochastic_invalid"] = True

        result["_indicator_signals"] = (
            build_indicator_signals(
                close=frame["close"],
                rsi_series=rsi_series,
                use_rsi=config.use_rsi,
                macd_data=macd_data,
                use_macd=config.use_macd,
                bollinger_bands=bands,
                use_bollinger=config.use_bollinger,
                stochastic_data=stochastic_data,
                use_stochastic=config.use_stochastic,
                stochastic_oversold=config.stochastic_oversold,
                stochastic_overbought=config.stochastic_overbought,
            )
            if any(
                (
                    config.use_rsi,
                    config.use_macd,
                    config.use_bollinger,
                    config.use_stochastic,
                )
            )
            else {}
        )
        return result
