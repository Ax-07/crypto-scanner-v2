from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.exceptions import BacktestCoverageError
from app.database.connection import Database
from app.domain.candles import Candle
from app.repositories.candle_repository import CandleRepository


class BacktestCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "coverage.sqlite3")
        await self.database.initialize()
        self.repository = CandleRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temporary.cleanup()

    async def test_complete_inclusive_exclusive_closed_only_read(self) -> None:
        await self.repository.upsert_many(
            [
                Candle(
                    "binance",
                    "spot",
                    "BTC/USDC",
                    "1m",
                    timestamp,
                    1,
                    2,
                    0.5,
                    1.5,
                    10,
                    timestamp + 60_000,
                    True,
                )
                for timestamp in (0, 60_000, 120_000)
            ]
            + [
                Candle(
                    "binance",
                    "spot",
                    "BTC/USDC",
                    "1m",
                    180_000,
                    1,
                    2,
                    0.5,
                    1.5,
                    10,
                    240_000,
                    False,
                )
            ]
        )
        report = await self.repository.validate_backtest_coverage(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            start_time=0,
            end_time=180_000,
        )
        self.assertTrue(report.is_complete)
        candles = await self.repository.get_candles_for_backtest(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            start_time=0,
            end_time=180_000,
        )
        self.assertEqual([item.open_time for item in candles], [0, 60_000, 120_000])

    async def test_incomplete_coverage_reports_gap_and_raises(self) -> None:
        await self.repository.upsert_many(
            [
                Candle(
                    "binance",
                    "spot",
                    "BTC/USDC",
                    "1m",
                    timestamp,
                    1,
                    2,
                    0.5,
                    1.5,
                    10,
                    timestamp + 60_000,
                    True,
                )
                for timestamp in (0, 120_000)
            ]
        )
        report = await self.repository.validate_backtest_coverage(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            start_time=0,
            end_time=180_000,
        )
        self.assertFalse(report.is_complete)
        self.assertEqual(report.missing_ranges, [(60_000, 120_000)])
        with self.assertRaises(BacktestCoverageError):
            await self.repository.get_candles_for_backtest(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                start_time=0,
                end_time=180_000,
            )


if __name__ == "__main__":
    unittest.main()
