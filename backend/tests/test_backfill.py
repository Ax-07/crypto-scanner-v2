from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.core.config import AppSettings
from app.database.connection import Database
from app.models.backfill import BackfillOptions, BackfillStatus
from app.repositories.backfill_repository import BackfillRepository
from app.repositories.candle_repository import CandleRepository
from app.repositories.market_repository import MarketRepository
from app.services.candle_backfill import CandleBackfillService, select_timeframes
from app.services.candle_sync import CandleSyncService
from app.services.market_catalog import MarketCatalogService


class FakeBackfillExchange:
    def __init__(self) -> None:
        self.timeframes = {"1m": "1m", "1h": "1h", "1d": "1d", "1M": "1M"}
        self.has = {"fetchOHLCV": True}
        self.markets = {
            "BTC/USDC": {
                "id": "BTCUSDC",
                "type": "spot",
                "spot": True,
                "quote": "USDC",
                "base": "BTC",
                "active": True,
            },
            "USDT/USDC": {
                "id": "USDTUSDC",
                "type": "spot",
                "spot": True,
                "quote": "USDC",
                "base": "USDT",
                "active": True,
            },
            "OLD/USDC": {
                "id": "OLDUSDC",
                "type": "spot",
                "spot": True,
                "quote": "USDC",
                "base": "OLD",
                "active": False,
            },
            "ETH/USDT": {
                "type": "spot",
                "spot": True,
                "quote": "USDT",
                "base": "ETH",
                "active": True,
            },
            "BTC/USDC:USDC": {
                "type": "swap",
                "spot": False,
                "quote": "USDC",
                "base": "BTC",
                "active": True,
            },
        }
        self.rows = {
            ("BTC/USDC", "1m"): [
                [0, 1, 2, 0.5, 1.5, 10],
                [60_000, 2, 3, 1, 2.5, 11],
                [120_000, 3, 4, 2, 3.5, 12],
            ]
        }
        self.fetch_calls: list[tuple[str, str, int]] = []
        self.closed = False

    async def load_markets(self):
        return self.markets

    async def fetch_ohlcv(self, symbol: str, *, timeframe: str, since: int, limit: int):
        self.fetch_calls.append((symbol, timeframe, since))
        return [row for row in self.rows.get((symbol, timeframe), []) if row[0] >= since][:limit]

    async def close(self) -> None:
        self.closed = True


class BackfillTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "backfill.sqlite3")
        await self.database.initialize()
        self.candles = CandleRepository(self.database)
        self.states = BackfillRepository(self.database)
        self.markets = MarketRepository(self.database)
        settings = AppSettings(
            database_path=self.database.path,
            candle_sync_page_limit=2,
        )
        self.sync = CandleSyncService(self.candles, settings)
        self.catalog = MarketCatalogService(self.markets)
        self.service = CandleBackfillService(
            self.candles,
            self.states,
            self.catalog,
            self.sync,
            self.database.path,
        )
        self.exchange = FakeBackfillExchange()

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temporary.cleanup()

    async def test_catalog_selects_all_spot_usdc_and_tracks_inactive(self) -> None:
        active = await self.catalog.discover(
            self.exchange,
            exchange_id="binance",
            market_type="spot",
            quote="USDC",
            include_inactive=False,
            persist=True,
        )
        self.assertEqual([item.symbol for item in active], ["BTC/USDC", "USDT/USDC"])
        self.assertIn("USDT/USDC", [item.symbol for item in active])
        all_markets = await self.catalog.discover(
            self.exchange,
            exchange_id="binance",
            market_type="spot",
            quote="USDC",
            include_inactive=True,
            persist=True,
        )
        self.assertEqual(
            [item.symbol for item in all_markets],
            ["BTC/USDC", "OLD/USDC", "USDT/USDC"],
        )
        self.exchange.markets["BTC/USDC"]["active"] = False
        await self.catalog.discover(
            self.exchange,
            exchange_id="binance",
            market_type="spot",
            quote="USDC",
            include_inactive=False,
            persist=True,
        )
        stored = await self.markets.list_markets("binance", "spot", "USDC", include_inactive=True)
        btc = next(item for item in stored if item.symbol == "BTC/USDC")
        self.assertFalse(btc.active)

    def test_timeframe_intersection_validation_and_order(self) -> None:
        selected, skipped = select_timeframes(self.exchange, ())
        self.assertEqual(selected[:3], ["1d", "1h", "1m"])
        self.assertNotIn("1M", selected)
        self.assertIn("3m", skipped)
        explicit, _ = select_timeframes(self.exchange, ("1m", "1d"))
        self.assertEqual(explicit, ["1d", "1m"])
        with self.assertRaises(ValueError):
            select_timeframes(self.exchange, ("1M",))

    async def test_dry_run_never_fetches_ohlcv(self) -> None:
        report = await self.service.run(
            self.exchange,
            BackfillOptions(
                symbols=("BTC/USDC",),
                timeframes=("1m",),
                execute=False,
            ),
        )
        self.assertFalse(report.execute)
        self.assertEqual(report.total_targets, 1)
        self.assertEqual(self.exchange.fetch_calls, [])
        self.assertEqual(await self.candles.count("binance", "spot", "BTC/USDC", "1m"), 0)

    async def test_pagination_checkpoint_upsert_resume_and_run_report(self) -> None:
        options = BackfillOptions(
            symbols=("BTC/USDC",),
            timeframes=("1m",),
            from_time=0,
            to_time=180_000,
            page_limit=2,
            execute=True,
        )
        report = await self.service.run(self.exchange, options)
        self.assertEqual(report.results[0].status, BackfillStatus.COMPLETED)
        self.assertEqual(report.results[0].pages, 2)
        self.assertEqual(await self.candles.count("binance", "spot", "BTC/USDC", "1m"), 3)
        state = await self.states.get_state("binance", "spot", "BTC/USDC", "1m")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.next_since, 180_000)
        second = await self.service.run(self.exchange, options)
        self.assertEqual(second.results[0].status, BackfillStatus.COMPLETED)
        self.assertEqual(await self.candles.count("binance", "spot", "BTC/USDC", "1m"), 3)
        runs = await self.states.list_runs()
        self.assertEqual(len(runs), 2)

    async def test_earliest_empty_and_interruption_state(self) -> None:
        options = BackfillOptions(
            symbols=("BTC/USDC",),
            timeframes=("1m",),
            page_limit=2,
            execute=True,
        )
        self.assertEqual(
            await self.service.find_earliest(self.exchange, options, "BTC/USDC", "1m"),
            0,
        )
        self.assertIsNone(
            await self.service.find_earliest(self.exchange, options, "MISSING/USDC", "1m")
        )

        with (
            patch.object(
                self.sync,
                "fetch_page",
                new=AsyncMock(side_effect=asyncio.CancelledError),
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await self.service._run_target(self.exchange, options, "BTC/USDC", "1m")
        state = await self.states.get_state("binance", "spot", "BTC/USDC", "1m")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.status, BackfillStatus.INTERRUPTED)


if __name__ == "__main__":
    unittest.main()
