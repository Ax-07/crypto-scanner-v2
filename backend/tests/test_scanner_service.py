from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pandas as pd

from app.core.settings import ScanConfig
from app.domain.backtesting import evaluate_information_set
from app.domain.candles import Candle, timeframe_milliseconds
from app.domain.indicator_bundle import build_indicator_signals
from app.domain.indicators import (
    calculate_bollinger_bands,
    calculate_confluence_score,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
)
from app.models.scanner import ScanResult, ScanStatus
from app.services.scan_manager import ScanManager
from app.services.scanner import ScannerService


def candle_frame(size: int = 220) -> pd.DataFrame:
    start = datetime.now(timezone.utc) - timedelta(hours=4 * (size + 2))
    close = [float(index + 10) for index in range(size)]
    times = [start + timedelta(hours=4 * index) for index in range(size)]
    return pd.DataFrame(
        {
            "timestamp": [time.timestamp() * 1000 for time in times],
            "time": pd.to_datetime(times, utc=True),
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [100.0] * size,
        }
    )


def descending_candle_frame(size: int = 220) -> pd.DataFrame:
    """Produit un historique complet dont le RSI ne rejette pas le scan."""
    frame = candle_frame(size)
    close = [float(size + 10 - index) for index in range(size)]
    frame["open"] = close
    frame["high"] = [value + 1 for value in close]
    frame["low"] = [value - 1 for value in close]
    frame["close"] = close
    return frame


def frame_to_candles(
    frame: pd.DataFrame,
    config: ScanConfig,
    symbol: str = "BTC/USDC",
) -> list[Candle]:
    """Convertit la fixture scanner pour l'oracle canonique réservé aux tests."""
    interval = timeframe_milliseconds(config.timeframe)
    return [
        Candle(
            exchange_id=config.exchange_id,
            market_type=config.market_type,
            symbol=symbol,
            timeframe=config.timeframe,
            open_time=int(row.timestamp),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
            close_time=int(row.timestamp) + interval,
            is_closed=True,
        )
        for row in frame.itertuples(index=False)
    ]


def minimal_config(**changes: object) -> ScanConfig:
    values: dict[str, object] = {
        "use_rsi": False,
        "use_ma": False,
        "use_macd": False,
        "use_bollinger": False,
        "use_stochastic": False,
        "use_confluence_score": False,
        "min_ohlcv_bars": 60,
    }
    values.update(changes)
    return ScanConfig(**values)


class ScannerIndicatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_filter_can_match_a_disabled_indicator_status(self) -> None:
        service = ScannerService(
            minimal_config(
                structured_signal_filters={
                    "version": 1,
                    "indicators": {
                        "macd": {
                            "match": "all",
                            "conditions": [{"field": "status", "values": ["disabled"]}],
                        }
                    },
                },
            )
        )
        with patch(
            "app.services.scanner.fetch_ohlcv",
            new=AsyncMock(return_value=candle_frame()),
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "success")
        self.assertIsNotNone(result)
        self.assertNotIn("macd", result.indicator_signals if result else {})

    async def test_structured_macd_filter_has_priority_over_legacy(self) -> None:
        service = ScannerService(
            minimal_config(
                use_macd=True,
                filter_macd_signal=["bearish"],
                structured_signal_filters={
                    "version": 1,
                    "indicators": {
                        "macd": {
                            "match": "all",
                            "conditions": [{"field": "direction", "values": ["bullish"]}],
                        }
                    },
                },
            )
        )
        with patch(
            "app.services.scanner.fetch_ohlcv",
            new=AsyncMock(return_value=candle_frame()),
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "success")
        self.assertIsNotNone(result)

    async def test_structured_macd_filter_can_reject_legacy_match(self) -> None:
        service = ScannerService(
            minimal_config(
                use_macd=True,
                filter_macd_signal=["bullish"],
                structured_signal_filters={
                    "version": 1,
                    "indicators": {
                        "macd": {
                            "match": "all",
                            "conditions": [{"field": "direction", "values": ["bearish"]}],
                        }
                    },
                },
            )
        )
        with patch(
            "app.services.scanner.fetch_ohlcv",
            new=AsyncMock(return_value=candle_frame()),
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "filtered")
        self.assertIsNone(result)

    async def test_disabled_rsi_is_not_calculated_or_filtered(self) -> None:
        service = ScannerService(minimal_config(rsi_threshold=0))
        with (
            patch("app.services.scanner.fetch_ohlcv", new=AsyncMock(return_value=candle_frame())),
            patch("app.services.scanner.calculate_rsi") as calculate_rsi,
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "success")
        self.assertIsNotNone(result)
        self.assertIsNone(result.rsi if result else 1)
        calculate_rsi.assert_not_called()

    async def test_disabled_macd_ignores_configured_filter(self) -> None:
        service = ScannerService(minimal_config(filter_macd_signal=["bullish"]))
        with patch(
            "app.services.scanner.fetch_ohlcv",
            new=AsyncMock(return_value=candle_frame()),
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "success")
        self.assertIsNotNone(result)
        self.assertIsNone(result.macd if result else 1)

    async def test_custom_ma_periods_use_two_shortest_periods(self) -> None:
        config = minimal_config(
            use_ma=True,
            use_sma=True,
            use_ema=False,
            sma_periods=[5, 8, 13],
            ma_timeframes=["4h"],
            min_trend_score=0,
        )
        service = ScannerService(config)
        with patch(
            "app.services.scanner.fetch_ohlcv",
            new=AsyncMock(return_value=candle_frame()),
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "success")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("sma_5_4h", result.moving_averages)
        self.assertIn("sma_8_4h", result.moving_averages)
        self.assertIn("sma_13_4h", result.moving_averages)
        self.assertNotIn("sma_20_4h", result.moving_averages)
        self.assertTrue(result.trends["4h"])

    async def test_missing_active_indicator_data_fails_minimum_before_confluence(self) -> None:
        config = minimal_config(
            use_macd=True,
            use_confluence_score=True,
            min_confluence_score=100,
            confluence_weights={"macd": 20},
        )
        service = ScannerService(config)
        with patch(
            "app.services.scanner.fetch_ohlcv",
            new=AsyncMock(return_value=candle_frame(5)),
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "error")
        self.assertIsNone(result)

    async def test_each_indicator_and_no_indicator_configuration_runs(self) -> None:
        configurations = [
            minimal_config(),
            minimal_config(use_rsi=True, rsi_threshold=100),
            minimal_config(
                use_ma=True,
                use_sma=True,
                use_ema=False,
                sma_periods=[5, 8],
                ma_timeframes=["4h"],
                min_trend_score=0,
            ),
            minimal_config(use_macd=True),
            minimal_config(use_bollinger=True),
            minimal_config(use_stochastic=True),
        ]
        for config in configurations:
            with self.subTest(config=config.model_dump()):
                service = ScannerService(config)
                with patch(
                    "app.services.scanner.fetch_ohlcv",
                    new=AsyncMock(return_value=candle_frame()),
                ):
                    status, _result = await service.analyze_symbol(object(), "BTC/USDC")
                self.assertIn(status, {"success", "filtered"})

    async def test_one_pass_calculation_counts_with_every_indicator_enabled(self) -> None:
        config = minimal_config(
            use_rsi=True,
            rsi_threshold=100,
            use_ma=True,
            use_sma=True,
            use_ema=True,
            sma_periods=[5, 8],
            ema_periods=[5, 8],
            ma_timeframes=["4h"],
            min_trend_score=0,
            use_macd=True,
            use_bollinger=True,
            use_stochastic=True,
            use_confluence_score=True,
            min_confluence_score=0,
        )
        service = ScannerService(config)
        with (
            patch(
                "app.services.scanner.fetch_ohlcv",
                new=AsyncMock(return_value=descending_candle_frame()),
            ) as fetch,
            patch(
                "app.services.scanner.calculate_rsi",
                wraps=calculate_rsi,
            ) as rsi,
            patch(
                "app.services.scanner.calculate_macd",
                wraps=calculate_macd,
            ) as macd,
            patch(
                "app.services.scanner.calculate_bollinger_bands",
                wraps=calculate_bollinger_bands,
            ) as bollinger,
            patch(
                "app.services.scanner.calculate_stochastic",
                wraps=calculate_stochastic,
            ) as stochastic,
            patch(
                "app.services.scanner.calculate_sma",
                wraps=calculate_sma,
            ) as sma,
            patch(
                "app.services.scanner.calculate_ema",
                wraps=calculate_ema,
            ) as ema,
            patch(
                "app.services.scanner.build_indicator_signals",
                wraps=build_indicator_signals,
            ) as builder,
            patch("app.domain.backtesting.evaluate_information_set") as canonical,
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "success")
        self.assertIsNotNone(result)
        fetch.assert_awaited_once()
        self.assertEqual(rsi.call_count, 1)
        self.assertEqual(macd.call_count, 1)
        self.assertEqual(bollinger.call_count, 1)
        self.assertEqual(stochastic.call_count, 1)
        self.assertEqual(sma.call_count, 2)
        self.assertEqual(ema.call_count, 2)
        self.assertEqual(builder.call_count, 1)
        canonical.assert_not_called()

    async def test_disabled_indicators_trigger_no_calculation_or_builder_entry(
        self,
    ) -> None:
        service = ScannerService(minimal_config())
        with (
            patch(
                "app.services.scanner.fetch_ohlcv",
                new=AsyncMock(return_value=candle_frame()),
            ),
            patch("app.services.scanner.calculate_rsi") as rsi,
            patch("app.services.scanner.calculate_macd") as macd,
            patch("app.services.scanner.calculate_bollinger_bands") as bollinger,
            patch("app.services.scanner.calculate_stochastic") as stochastic,
            patch("app.services.scanner.calculate_sma") as sma,
            patch("app.services.scanner.calculate_ema") as ema,
            patch("app.services.scanner.build_indicator_signals") as builder,
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "success")
        self.assertIsNotNone(result)
        for calculation in (rsi, macd, bollinger, stochastic, sma, ema, builder):
            calculation.assert_not_called()
        assert result is not None
        self.assertEqual(result.indicator_signals, {})
        self.assertEqual(result.confluence_breakdown, {})

    async def test_rsi_rejection_stops_before_other_indicator_calculations(
        self,
    ) -> None:
        service = ScannerService(
            minimal_config(
                use_rsi=True,
                rsi_threshold=35,
                use_macd=True,
                use_bollinger=True,
                use_stochastic=True,
            )
        )
        with (
            patch(
                "app.services.scanner.fetch_ohlcv",
                new=AsyncMock(return_value=candle_frame()),
            ),
            patch(
                "app.services.scanner.calculate_rsi",
                wraps=calculate_rsi,
            ) as rsi,
            patch("app.services.scanner.calculate_macd") as macd,
            patch("app.services.scanner.calculate_bollinger_bands") as bollinger,
            patch("app.services.scanner.calculate_stochastic") as stochastic,
            patch("app.services.scanner.build_indicator_signals") as builder,
        ):
            status, result = await service.analyze_symbol(object(), "BTC/USDC")

        self.assertEqual(status, "filtered")
        self.assertIsNone(result)
        self.assertEqual(rsi.call_count, 1)
        for calculation in (macd, bollinger, stochastic, builder):
            calculation.assert_not_called()

    async def test_scanner_decision_and_public_classes_match_canonical_oracle(
        self,
    ) -> None:
        configurations = [
            minimal_config(use_macd=True, filter_macd_signal=["bearish"]),
            minimal_config(
                use_macd=True,
                structured_signal_filters={
                    "version": 1,
                    "indicators": {
                        "macd": {
                            "match": "all",
                            "conditions": [{"field": "direction", "values": ["bearish"]}],
                        }
                    },
                },
            ),
            minimal_config(
                use_macd=True,
                filter_macd_signal=["bullish"],
                structured_signal_filters={
                    "version": 1,
                    "indicators": {
                        "macd": {
                            "match": "all",
                            "conditions": [],
                        }
                    },
                },
            ),
            minimal_config(
                use_macd=True,
                filter_macd_signal=["bearish"],
                structured_signal_filters={
                    "version": 1,
                    "indicators": {
                        "macd": {
                            "match": "all",
                            "conditions": [{"field": "direction", "values": ["bullish"]}],
                        }
                    },
                },
            ),
            minimal_config(
                structured_signal_filters={
                    "version": 1,
                    "indicators": {
                        "macd": {
                            "match": "all",
                            "conditions": [{"field": "status", "values": ["disabled"]}],
                        }
                    },
                },
            ),
        ]
        for config in configurations:
            with self.subTest(config=config.model_dump(mode="json")):
                service = ScannerService(config)
                with patch(
                    "app.services.scanner.fetch_ohlcv",
                    new=AsyncMock(return_value=descending_candle_frame()),
                ):
                    outcome = await service.analyze_symbol(object(), "BTC/USDC")

                cached = service._candle_cache[("BTC/USDC", config.timeframe)]
                assert cached is not None
                primary = frame_to_candles(cached, config)
                decision_time = primary[-1].close_time
                assert decision_time is not None
                canonical = evaluate_information_set(
                    job_id="parity-oracle",
                    symbol="BTC/USDC",
                    decision_time_ms=decision_time,
                    primary=primary,
                    trend_candles={config.timeframe: primary},
                    config=config,
                )

                self.assertEqual(outcome.status == "success", canonical.accepted)
                if outcome.result is not None:
                    self.assertEqual(outcome.result.rsi, canonical.rsi)
                    self.assertEqual(
                        outcome.result.macd_signal_type,
                        canonical.macd_signal,
                    )
                    self.assertEqual(
                        outcome.result.bb_position,
                        canonical.bollinger_position,
                    )
                    self.assertEqual(
                        outcome.result.stoch_signal,
                        canonical.stochastic_signal,
                    )
                    self.assertEqual(
                        outcome.result.indicator_signals,
                        canonical.indicator_signals,
                    )


class ConfluenceTests(unittest.TestCase):
    def test_rsi_and_macd_weights_are_normalized_to_one_hundred(self) -> None:
        result = calculate_confluence_score(
            rsi_value=20,
            rsi_threshold=35,
            trend_score=None,
            max_trend_score=0,
            macd_signal="bullish",
            bb_position=None,
            stoch_signal=None,
            weights={"rsi": 20, "macd": 20},
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["effective_weights"], {"rsi": 50.0, "macd": 50.0})

    def test_no_calculated_indicator_returns_none(self) -> None:
        result = calculate_confluence_score(
            rsi_value=None,
            rsi_threshold=35,
            trend_score=None,
            max_trend_score=0,
            macd_signal=None,
            bb_position=None,
            stoch_signal=None,
            weights={},
        )
        self.assertIsNone(result)


class ScanLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_pair_error_does_not_stop_other_pairs(self) -> None:
        exchange = AsyncMock()
        service = ScannerService(minimal_config(max_concurrency=2))

        async def analyze(_exchange: object, symbol: str) -> tuple[str, ScanResult | None]:
            if symbol == "BAD/USDC":
                raise RuntimeError("pair failure")
            return "success", ScanResult(symbol=symbol, timeframe="4h")

        service.analyze_symbol = analyze  # type: ignore[method-assign]
        updates = []

        async def update(progress: object) -> None:
            updates.append(progress)

        with (
            patch("app.services.scanner.create_exchange", return_value=exchange),
            patch(
                "app.services.scanner.load_filtered_symbols",
                new=AsyncMock(return_value=["BAD/USDC", "BTC/USDC"]),
            ),
        ):
            results = await service.scan(update)

        self.assertEqual([result.symbol for result in results], ["BTC/USDC"])
        self.assertEqual(updates[-1].errors, 1)
        self.assertEqual(updates[-1].successful, 1)
        exchange.close.assert_awaited_once()

    async def test_cancellation_sets_status_and_releases_service(self) -> None:
        released = asyncio.Event()

        class BlockingScanner:
            def __init__(self, _config: ScanConfig) -> None:
                pass

            async def scan(self, _callback: object) -> list[ScanResult]:
                try:
                    await asyncio.Event().wait()
                finally:
                    released.set()

        manager = ScanManager()
        with patch("app.services.scan_manager.ScannerService", BlockingScanner):
            job = await manager.create_job(minimal_config())
            await asyncio.sleep(0)
            await manager.cancel_job(job.id)
            await manager._tasks[job.id]

        self.assertEqual(job.status, ScanStatus.CANCELLED)
        self.assertTrue(released.is_set())

    async def test_scanner_cancellation_closes_exchange(self) -> None:
        exchange = AsyncMock()
        started = asyncio.Event()

        async def block(_exchange: object, _symbol: str) -> tuple[str, None]:
            started.set()
            await asyncio.Event().wait()
            return "filtered", None

        service = ScannerService(minimal_config(max_concurrency=1))
        service.analyze_symbol = block  # type: ignore[method-assign]
        with (
            patch("app.services.scanner.create_exchange", return_value=exchange),
            patch(
                "app.services.scanner.load_filtered_symbols",
                new=AsyncMock(return_value=["BTC/USDC", "ETH/USDC"]),
            ),
        ):
            task = asyncio.create_task(service.scan())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        exchange.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
