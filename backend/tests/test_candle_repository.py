from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from app.database.connection import Database
from app.database.schema import MIGRATION_1, MIGRATION_2, MIGRATION_3, MIGRATIONS, SCHEMA_VERSION
from app.domain.candles import Candle, find_missing_ranges
from app.domain.ohlcv_fingerprint import InputDataStreamFingerprint, aggregate_input_fingerprints
from app.models.backtest import BacktestConfig, BacktestJob
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository


def candle(open_time: int, *, close: float = 1.5, closed: bool = True) -> Candle:
    return Candle(
        exchange_id="binance",
        market_type="spot",
        symbol="BTC/USDC",
        timeframe="1m",
        open_time=open_time,
        open=1,
        high=2,
        low=0.5,
        close=close,
        volume=10,
        close_time=open_time + 60_000,
        is_closed=closed,
    )


class DatabaseAndRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "nested" / "candles.sqlite3"
        self.database = Database(self.path)
        await self.database.initialize()
        self.repository = CandleRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temporary.cleanup()

    async def test_database_migrations_indexes_pragmas_and_reopen(self) -> None:
        self.assertTrue(self.path.is_file())
        async with self.database.connection() as connection:
            tables = {
                row[0]
                for row in await (
                    await connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                ).fetchall()
            }
            indexes = {
                row[0]
                for row in await (
                    await connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
                ).fetchall()
            }
            journal = await (await connection.execute("PRAGMA journal_mode")).fetchone()
            foreign_keys = await (await connection.execute("PRAGMA foreign_keys")).fetchone()
        self.assertIn("candles", tables)
        self.assertIn("markets", tables)
        self.assertIn("candle_sync_state", tables)
        self.assertIn("backfill_runs", tables)
        self.assertIn("candle_gaps", tables)
        self.assertIn("candle_history_bounds", tables)
        self.assertIn("schema_migrations", tables)
        self.assertIn("ml_v2_source_claims", tables)
        self.assertIn("idx_candles_market_time", indexes)
        self.assertEqual(str(journal[0]).lower(), "wal")
        self.assertEqual(foreign_keys[0], 1)
        await self.database.initialize()
        async with self.database.connection() as connection:
            versions = await (
                await connection.execute("SELECT COUNT(*) FROM schema_migrations")
            ).fetchone()
        self.assertEqual(versions[0], SCHEMA_VERSION)

    async def test_migrations_9_and_10_preserve_an_existing_version_8_database(self) -> None:
        legacy_path = Path(self.temporary.name) / "legacy-v8.sqlite3"
        async with aiosqlite.connect(legacy_path) as connection:
            await connection.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at INTEGER NOT NULL
                )
                """)
            for version in range(1, 9):
                await connection.executescript(MIGRATIONS[version])
                await connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 0)",
                    (version,),
                )
            await connection.execute("""
                INSERT INTO backtest_jobs (
                    id, status, config_json, progress_json, warnings_json,
                    created_at, updated_at
                ) VALUES ('legacy-job', 'pending', '{}', '{}', '[]', 0, 0)
                """)
            await connection.commit()

        legacy = Database(legacy_path)
        await legacy.initialize()
        async with legacy.connection() as connection:
            version = await (
                await connection.execute("SELECT MAX(version) FROM schema_migrations")
            ).fetchone()
            legacy_job = await (
                await connection.execute(
                    "SELECT id, status FROM backtest_jobs WHERE id='legacy-job'"
                )
            ).fetchone()
            claims_table = await (await connection.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='ml_v2_source_claims'
                    """)).fetchone()
        self.assertEqual(version[0], 10)
        self.assertEqual(tuple(legacy_job), ("legacy-job", "pending"))
        self.assertEqual(claims_table[0], "ml_v2_source_claims")
        await legacy.close()

    async def test_migration_10_preserves_true_schema_9_history_and_null_provenance(
        self,
    ) -> None:
        legacy_path = Path(self.temporary.name) / "legacy-v9.sqlite3"
        async with aiosqlite.connect(legacy_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute(
                "CREATE TABLE schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)"
            )
            for version in range(1, 10):
                await connection.executescript(MIGRATIONS[version])
                await connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 0)",
                    (version,),
                )
            for job_id in ("inline-history", "phase1-v2"):
                await connection.execute(
                    """
                    INSERT INTO backtest_jobs (
                        id, status, config_json, progress_json, warnings_json,
                        created_at, updated_at
                    ) VALUES (?, 'completed', '{}', '{}', '[]', 0, 0)
                    """,
                    (job_id,),
                )
            observation = await connection.execute("""
                INSERT INTO backtest_observations (
                    job_id, symbol, decision_time, snapshot_status, accepted,
                    payload_json
                ) VALUES ('phase1-v2', 'BTC/USDC', 1, 'confirmed', 1, '{}')
                """)
            await connection.execute(
                """
                INSERT INTO backtest_outcomes (
                    job_id, observation_id, horizon, payload_json
                ) VALUES ('phase1-v2', ?, 6, '{}')
                """,
                (observation.lastrowid,),
            )
            await connection.execute("""
                INSERT INTO ml_v2_source_claims (
                    source_identity, job_id, algorithm_version, created_at, updated_at
                ) VALUES ('phase1-identity', 'phase1-v2', 'signal-evaluation-v3', 0, 0)
                """)
            await connection.commit()

        migrated = Database(legacy_path)
        await migrated.initialize()
        await migrated.initialize()
        async with migrated.connection() as connection:
            jobs = await (
                await connection.execute("SELECT id FROM backtest_jobs ORDER BY id")
            ).fetchall()
            counts = []
            for table in ("backtest_observations", "backtest_outcomes"):
                row = await (await connection.execute(f"SELECT COUNT(*) FROM {table}")).fetchone()
                counts.append(row[0])
            claim = await (
                await connection.execute(
                    "SELECT job_id, input_data_fingerprint FROM ml_v2_source_claims"
                )
            ).fetchone()
            strong_count = await (
                await connection.execute("SELECT COUNT(*) FROM ml_v2_source_inputs")
            ).fetchone()
            integrity = await (await connection.execute("PRAGMA integrity_check")).fetchone()
        self.assertEqual([row[0] for row in jobs], ["inline-history", "phase1-v2"])
        self.assertEqual(counts, [1, 1])
        self.assertEqual(tuple(claim), ("phase1-v2", None))
        self.assertEqual(strong_count[0], 0)
        self.assertEqual(integrity[0], "ok")

        repository = BacktestRepository(migrated)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        new_job = BacktestJob(
            id="fingerprinted-v2",
            config=BacktestConfig(
                symbols=["BTC/USDC"], start=start, end=start + timedelta(hours=1)
            ),
        )
        stream = InputDataStreamFingerprint(
            role="primary",
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1h",
            requested_start_ms=1,
            requested_end_ms=2,
            effective_first_open_time_ms=1,
            effective_last_open_time_ms=1,
            candle_count=1,
            warmup_bars=0,
            future_bars=0,
            gaps_validated=True,
            fingerprint="sha256:" + "1" * 64,
        )
        fingerprint = aggregate_input_fingerprints("new-identity", (stream,))
        selected, created = await repository.claim_ml_v2_source(
            "new-identity",
            new_job,
            algorithm_version=new_job.algorithm_version,
            input_fingerprint=fingerprint,
        )
        self.assertTrue(created)
        self.assertEqual(selected, new_job.id)
        self.assertIsNotNone(await repository.get_ml_v2_source_input(new_job.id))
        await migrated.close()

    async def test_upsert_latest_range_filters_bounds_and_no_duplicate(self) -> None:
        self.assertEqual(await self.repository.upsert_many([]), 0)
        await self.repository.upsert_many(
            [candle(0), candle(60_000, closed=False), candle(120_000)]
        )
        await self.repository.upsert_many([candle(60_000, close=9, closed=True)])
        self.assertEqual(
            await self.repository.count("binance", "spot", "BTC/USDC", "1m"),
            3,
        )
        latest = await self.repository.get_latest("binance", "spot", "BTC/USDC", "1m", 2)
        self.assertEqual([item.open_time for item in latest], [60_000, 120_000])
        self.assertEqual(latest[0].close, 9)
        closed = await self.repository.get_latest(
            "binance", "spot", "BTC/USDC", "1m", 10, closed_only=True
        )
        self.assertEqual(len(closed), 3)
        ranged = await self.repository.get_range(
            "binance",
            "spot",
            "BTC/USDC",
            "1m",
            from_time=60_000,
            to_time=120_000,
        )
        self.assertEqual([item.open_time for item in ranged], [60_000])
        self.assertEqual(
            await self.repository.get_first_open_time("binance", "spot", "BTC/USDC", "1m"),
            0,
        )
        self.assertEqual(
            await self.repository.get_last_open_time("binance", "spot", "BTC/USDC", "1m"),
            120_000,
        )

    async def test_cursor_pagination_is_exclusive_ordered_and_closed_filtered(self) -> None:
        await self.repository.upsert_many(
            [
                candle(0),
                candle(60_000),
                candle(120_000, closed=False),
                candle(180_000),
            ]
        )
        page = await self.repository.get_candles_before(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            before_open_time=180_000,
            limit=2,
        )
        self.assertEqual([item.open_time for item in page], [60_000, 120_000])
        closed = await self.repository.get_candles_before(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            before_open_time=180_000,
            limit=5,
            closed_only=True,
        )
        self.assertEqual([item.open_time for item in closed], [0, 60_000])
        after = await self.repository.get_candles_after(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            after_open_time=60_000,
            limit=5,
        )
        self.assertEqual([item.open_time for item in after], [120_000, 180_000])
        async with self.database.connection() as connection:
            plan = await (
                await connection.execute(
                    """
                    EXPLAIN QUERY PLAN
                    SELECT open_time FROM candles
                    WHERE exchange_id=? AND market_type=? AND symbol=? AND timeframe=?
                      AND open_time<?
                    ORDER BY open_time DESC LIMIT ?
                    """,
                    ("binance", "spot", "BTC/USDC", "1m", 180_000, 2),
                )
            ).fetchall()
        self.assertIn("idx_candles_market_time", " ".join(str(row[3]) for row in plan))

    async def test_window_complete_range_and_persistent_earliest_bound(self) -> None:
        await self.repository.upsert_many(
            [candle(0), candle(60_000), candle(120_000), candle(180_000)]
        )
        window = await self.repository.get_window(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            anchor_open_time=120_000,
            before_count=2,
            after_count=2,
        )
        self.assertEqual([item.open_time for item in window], [0, 60_000, 120_000, 180_000])
        self.assertTrue(
            await self.repository.has_complete_range(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                start_time=0,
                end_time=240_000,
            )
        )
        await self.repository.set_exchange_earliest_verified("binance", "spot", "BTC/USDC", "1m", 0)
        metadata = await self.repository.refresh_history_metadata(
            "binance", "spot", "BTC/USDC", "1m"
        )
        self.assertTrue(metadata.exchange_earliest_verified)
        self.assertEqual(metadata.exchange_earliest_time, 0)
        self.assertFalse(metadata.has_more_before)

    async def test_repairs_wrong_metadata_without_deleting_candles(self) -> None:
        await self.repository.upsert_many([candle(120_000)])
        await self.repository.set_exchange_earliest_verified(
            "binance", "spot", "BTC/USDC", "1m", 120_000
        )
        await self.repository.set_history_error(
            "binance", "spot", "BTC/USDC", "1m", "ancienne erreur"
        )
        repaired = await self.repository.reset_history_metadata(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
        )
        metadata = await self.repository.get_history_metadata("binance", "spot", "BTC/USDC", "1m")
        self.assertEqual(repaired, 1)
        self.assertIsNone(metadata.exchange_earliest_time)
        self.assertFalse(metadata.exchange_earliest_verified)
        self.assertTrue(metadata.has_more_before)
        self.assertIsNone(metadata.last_error)
        self.assertEqual(
            await self.repository.count("binance", "spot", "BTC/USDC", "1m"),
            1,
        )

    async def test_bulk_repair_only_resets_verified_targets(self) -> None:
        await self.repository.set_exchange_earliest_verified("binance", "spot", "ETH/USDC", "1h", 0)
        await self.repository.refresh_history_metadata("binance", "spot", "SOL/USDC", "1d")
        repaired = await self.repository.reset_history_metadata()
        eth = await self.repository.get_history_metadata("binance", "spot", "ETH/USDC", "1h")
        sol = await self.repository.get_history_metadata("binance", "spot", "SOL/USDC", "1d")
        self.assertEqual(repaired, 1)
        self.assertFalse(eth.exchange_earliest_verified)
        self.assertTrue(eth.has_more_before)
        self.assertFalse(sol.exchange_earliest_verified)
        self.assertTrue(sol.has_more_before)

    async def test_migration_repairs_legacy_bounds_and_preserves_candles(self) -> None:
        legacy_path = Path(self.temporary.name) / "legacy.sqlite3"
        async with aiosqlite.connect(legacy_path) as connection:
            await connection.executescript(MIGRATION_1)
            await connection.executescript(MIGRATION_2)
            await connection.executescript(MIGRATION_3)
            await connection.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at INTEGER NOT NULL
                )
                """)
            await connection.executemany(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 0)",
                [(1,), (2,), (3,)],
            )
            await connection.execute("""
                INSERT INTO candles VALUES (
                    'binance', 'spot', 'ETH/USDC', '1h', 120000,
                    1, 2, 0.5, 1.5, 10, 180000, 1, 0
                )
                """)
            await connection.execute("""
                INSERT INTO candle_history_bounds VALUES (
                    'binance', 'spot', 'ETH/USDC', '1h', 1, 120000, 0
                )
                """)
            await connection.commit()

        migrated = Database(legacy_path)
        await migrated.initialize()
        repository = CandleRepository(migrated)
        metadata = await repository.get_history_metadata("binance", "spot", "ETH/USDC", "1h")
        self.assertIsNone(metadata.exchange_earliest_time)
        self.assertFalse(metadata.exchange_earliest_verified)
        self.assertTrue(metadata.has_more_before)
        self.assertIsNone(metadata.last_error)
        self.assertEqual(
            await repository.count("binance", "spot", "ETH/USDC", "1h"),
            1,
        )
        await migrated.close()

    async def test_open_candle_operations_concurrent_read_and_atomic_rollback(self) -> None:
        await self.repository.upsert_many([candle(0), candle(60_000, closed=False)])
        read, written = await asyncio.gather(
            self.repository.get_latest("binance", "spot", "BTC/USDC", "1m", 10),
            self.repository.upsert_many([candle(120_000)]),
        )
        self.assertTrue(read)
        self.assertEqual(written, 1)
        deleted = await self.repository.delete_open_candle("binance", "spot", "BTC/USDC", "1m")
        self.assertEqual(deleted, 1)

        invalid = candle(180_000)
        object.__setattr__(invalid, "open", None)
        with self.assertRaises(aiosqlite.IntegrityError):
            await self.repository.upsert_many([candle(180_000), invalid])
        self.assertEqual(
            await self.repository.count("binance", "spot", "BTC/USDC", "1m"),
            2,
        )

    async def test_missing_ranges_and_repository_detection(self) -> None:
        self.assertEqual(find_missing_ranges([], "1m", now_ms=1_000_000), [])
        self.assertEqual(
            find_missing_ranges([0, 60_000, 180_000, 300_000], "1m", now_ms=300_000),
            [(120_000, 180_000), (240_000, 300_000)],
        )
        await self.repository.upsert_many([candle(0), candle(120_000), candle(180_000)])
        self.assertEqual(
            await self.repository.find_missing_ranges(
                "binance",
                "spot",
                "BTC/USDC",
                "1m",
                now_ms=300_000,
            ),
            [(60_000, 120_000)],
        )


if __name__ == "__main__":
    unittest.main()
