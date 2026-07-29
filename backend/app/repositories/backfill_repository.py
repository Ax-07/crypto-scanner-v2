"""Checkpoints, exécutions et trous du backfill historique."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.database.connection import Database
from app.models.backfill import BackfillStatus, SyncState
from app.domain.candles import timeframe_milliseconds


def now_ms() -> int:
    """Retourne l'heure UTC en millisecondes."""
    return int(datetime.now(timezone.utc).timestamp() * 1_000)


class BackfillRepository:
    """Persiste l'avancement après chaque page validée."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def get_state(
        self, exchange_id: str, market_type: str, symbol: str, timeframe: str
    ) -> SyncState | None:
        """Lit le checkpoint d'une cible."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM candle_sync_state WHERE exchange_id=? AND "
                "market_type=? AND symbol=? AND timeframe=?",
                (exchange_id, market_type, symbol, timeframe),
            )
            row = await cursor.fetchone()
        return self._state_from_row(row) if row else None

    async def save_state(self, state: SyncState) -> None:
        """Insère ou remplace intégralement un checkpoint."""
        state.updated_at = now_ms()
        values = (
            state.exchange_id,
            state.market_type,
            state.symbol,
            state.timeframe,
            state.status.value,
            state.requested_from,
            state.requested_to,
            state.earliest_available_time,
            state.latest_available_time,
            state.next_since,
            state.pages_downloaded,
            state.candles_downloaded,
            state.candles_upserted,
            state.retry_count,
            state.gap_count,
            state.last_error,
            state.started_at,
            state.completed_at,
            state.updated_at,
        )
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO candle_sync_state VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                ) ON CONFLICT(exchange_id, market_type, symbol, timeframe)
                DO UPDATE SET status=excluded.status,
                    requested_from=excluded.requested_from,
                    requested_to=excluded.requested_to,
                    earliest_available_time=excluded.earliest_available_time,
                    latest_available_time=excluded.latest_available_time,
                    next_since=excluded.next_since,
                    pages_downloaded=excluded.pages_downloaded,
                    candles_downloaded=excluded.candles_downloaded,
                    candles_upserted=excluded.candles_upserted,
                    retry_count=excluded.retry_count, gap_count=excluded.gap_count,
                    last_error=excluded.last_error, started_at=excluded.started_at,
                    completed_at=excluded.completed_at, updated_at=excluded.updated_at
                """,
                values,
            )
            await connection.commit()

    async def reset_state(
        self, exchange_id: str, market_type: str, symbol: str, timeframe: str
    ) -> None:
        """Supprime uniquement le checkpoint ciblé, jamais les autres données."""
        async with self.database.connection() as connection:
            await connection.execute(
                "DELETE FROM candle_sync_state WHERE exchange_id=? AND "
                "market_type=? AND symbol=? AND timeframe=?",
                (exchange_id, market_type, symbol, timeframe),
            )
            await connection.commit()

    async def create_run(
        self,
        run_id: str,
        exchange_id: str,
        market_type: str,
        quote: str,
        total_targets: int,
        options: dict[str, object],
    ) -> None:
        """Crée une exécution globale persistante."""
        current = now_ms()
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO backfill_runs (
                    id, exchange_id, market_type, quote, status, total_targets,
                    options_json, created_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    exchange_id,
                    market_type,
                    quote,
                    BackfillStatus.RUNNING.value,
                    total_targets,
                    json.dumps(options, sort_keys=True),
                    current,
                    current,
                ),
            )
            await connection.commit()

    async def finish_run(
        self,
        run_id: str,
        status: BackfillStatus,
        *,
        completed: int,
        partial: int,
        failed: int,
        interrupted: int,
        pages: int,
        candles: int,
        last_error: str | None = None,
    ) -> None:
        """Enregistre les compteurs terminaux d'une exécution."""
        async with self.database.connection() as connection:
            await connection.execute(
                """
                UPDATE backfill_runs SET status=?, completed_targets=?,
                    partial_targets=?, failed_targets=?, interrupted_targets=?,
                    total_pages=?, total_candles=?, completed_at=?, last_error=?
                WHERE id=?
                """,
                (
                    status.value,
                    completed,
                    partial,
                    failed,
                    interrupted,
                    pages,
                    candles,
                    now_ms(),
                    last_error,
                    run_id,
                ),
            )
            await connection.commit()

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retourne les exécutions les plus récentes."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM backfill_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Retourne une exécution précise."""
        async with self.database.connection() as connection:
            cursor = await connection.execute("SELECT * FROM backfill_runs WHERE id=?", (run_id,))
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def replace_gaps(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        gaps: list[tuple[int, int]],
    ) -> None:
        """Actualise les trous ouverts d'une cible."""
        current = now_ms()
        interval = timeframe_milliseconds(timeframe)
        async with self.database.connection() as connection:
            await connection.execute(
                "DELETE FROM candle_gaps WHERE exchange_id=? AND market_type=? "
                "AND symbol=? AND timeframe=? AND status='open'",
                (exchange_id, market_type, symbol, timeframe),
            )
            await connection.executemany(
                """
                INSERT INTO candle_gaps (
                    exchange_id, market_type, symbol, timeframe, gap_start,
                    gap_end, expected_candles, status, detected_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                ON CONFLICT DO UPDATE SET expected_candles=excluded.expected_candles,
                    status='open', updated_at=excluded.updated_at
                """,
                [
                    (
                        exchange_id,
                        market_type,
                        symbol,
                        timeframe,
                        start,
                        end,
                        max(0, (end - start) // interval),
                        current,
                        current,
                    )
                    for start, end in gaps
                ],
            )
            await connection.commit()

    @staticmethod
    def _state_from_row(row: Any) -> SyncState:
        return SyncState(
            exchange_id=str(row["exchange_id"]),
            market_type=str(row["market_type"]),
            symbol=str(row["symbol"]),
            timeframe=str(row["timeframe"]),
            status=BackfillStatus(str(row["status"])),
            requested_from=row["requested_from"],
            requested_to=row["requested_to"],
            earliest_available_time=row["earliest_available_time"],
            latest_available_time=row["latest_available_time"],
            next_since=row["next_since"],
            pages_downloaded=int(row["pages_downloaded"]),
            candles_downloaded=int(row["candles_downloaded"]),
            candles_upserted=int(row["candles_upserted"]),
            retry_count=int(row["retry_count"]),
            gap_count=int(row["gap_count"]),
            last_error=row["last_error"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            updated_at=int(row["updated_at"]),
        )
