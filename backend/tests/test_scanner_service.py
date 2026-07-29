from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pandas as pd

from app.core.settings import ScanConfig
from app.models.scanner import ScanResult, ScanStatus
from app.domain.indicators import calculate_confluence_score
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
            patch("app.services.scanner.get_latest_rsi") as calculate_rsi,
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
