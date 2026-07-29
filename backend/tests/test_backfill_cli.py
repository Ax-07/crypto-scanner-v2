from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite

from app.cli.backfill_candles import build_parser, main, options_from_args
from app.cli.backup_database import backup
from app.cli.repair_history_metadata import repair
from app.database.connection import Database


class BackfillCliTests(unittest.TestCase):
    def test_options_explicit_timeframes_dates_and_execute(self) -> None:
        parser = build_parser()
        options = options_from_args(
            parser.parse_args(
                [
                    "--symbol",
                    "BTC/USDC",
                    "--timeframes",
                    "1m",
                    "1h",
                    "--from-date",
                    "2020-01-01",
                    "--to-date",
                    "2020-01-02",
                    "--execute",
                ]
            )
        )
        self.assertEqual(options.symbols, ("BTC/USDC",))
        self.assertEqual(options.timeframes, ("1m", "1h"))
        self.assertTrue(options.execute)
        self.assertLess(options.from_time or 0, options.to_time or 0)

    def test_invalid_timeframe_returns_nonzero_without_network(self) -> None:
        self.assertEqual(main(["--timeframes", "1M"]), 2)


class BackupTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_backup_api_creates_consistent_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.sqlite3"
            destination = Path(temporary) / "backup.sqlite3"
            database = Database(source)
            await database.initialize()
            with patch.dict("os.environ", {"DATABASE_PATH": str(source)}):
                await backup(destination)
            async with aiosqlite.connect(destination) as connection:
                row = await (
                    await connection.execute("SELECT COUNT(*) FROM schema_migrations")
                ).fetchone()
            self.assertEqual(row[0], 7)

    async def test_targeted_history_metadata_repair_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "repair.sqlite3"
            with patch.dict("os.environ", {"DATABASE_PATH": str(source)}):
                repaired = await repair(
                    exchange_id="binance",
                    market_type="spot",
                    symbol="ETH/USDC",
                    timeframe="1h",
                )
            self.assertEqual(repaired, 1)
            async with aiosqlite.connect(source) as connection:
                row = await (await connection.execute("""
                        SELECT exchange_earliest_time, exchange_earliest_verified,
                               has_more_before, last_error
                        FROM candle_history_bounds
                        WHERE symbol='ETH/USDC' AND timeframe='1h'
                        """)).fetchone()
            self.assertEqual(tuple(row), (None, 0, 1, None))


if __name__ == "__main__":
    unittest.main()
