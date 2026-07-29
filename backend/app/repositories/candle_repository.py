"""Requêtes SQLite paramétrées pour les bougies OHLCV."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from app.database.connection import Database
from app.core.exceptions import BacktestCoverageError
from app.domain.candles import Candle, timeframe_milliseconds
from app.models.backfill import CoverageReport

MARKET_FILTER = "exchange_id = ? AND market_type = ? AND symbol = ? AND timeframe = ?"
CANDLE_COLUMNS = (
    "exchange_id, market_type, symbol, timeframe, open_time, open, high, low, "
    "close, volume, close_time, is_closed"
)


@dataclass(frozen=True, slots=True)
class HistoryMetadata:
    """État exchange explicite, indépendant de la couverture SQLite locale."""

    exchange_earliest_time: int | None = None
    exchange_earliest_verified: bool = False
    has_more_before: bool = True
    last_error: str | None = None


class CandleRepository:
    """Persiste et relit les bougies sans logique réseau ou d'indicateurs."""

    def __init__(self, database: Database) -> None:
        """Associe le repository à une fabrique de connexions."""
        self.database = database

    async def upsert_many(self, candles: list[Candle]) -> int:
        """Insère ou remplace atomiquement un lot et retourne sa taille."""
        if not candles:
            return 0
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1_000)
        rows = [
            (
                candle.exchange_id,
                candle.market_type,
                candle.symbol,
                candle.timeframe,
                candle.open_time,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.close_time,
                int(candle.is_closed),
                updated_at,
            )
            for candle in candles
        ]
        sql = """
            INSERT INTO candles (
                exchange_id, market_type, symbol, timeframe, open_time,
                open, high, low, close, volume, close_time, is_closed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (exchange_id, market_type, symbol, timeframe, open_time)
            DO UPDATE SET
                open = excluded.open, high = excluded.high, low = excluded.low,
                close = excluded.close, volume = excluded.volume,
                close_time = excluded.close_time, is_closed = excluded.is_closed,
                updated_at = excluded.updated_at
        """
        async with self.database.connection() as connection:
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.executemany(sql, rows)
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return len(rows)

    async def get_latest(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        limit: int,
        *,
        closed_only: bool = False,
    ) -> list[Candle]:
        """Retourne les dernières bougies en ordre chronologique."""
        closed = " AND is_closed = 1" if closed_only else ""
        sql = (
            f"SELECT {CANDLE_COLUMNS} FROM candles WHERE {MARKET_FILTER}{closed} "
            "ORDER BY open_time DESC LIMIT ?"
        )
        params = (exchange_id, market_type, symbol, timeframe, limit)
        async with self.database.connection() as connection:
            cursor = await connection.execute(sql, params)
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in reversed(list(rows))]

    async def get_candles_before(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        before_open_time: int | None,
        limit: int,
        closed_only: bool = False,
    ) -> list[Candle]:
        """Paginate vers le passé par curseur, sans ``OFFSET``."""
        clauses = [MARKET_FILTER]
        params: list[str | int] = [exchange_id, market_type, symbol, timeframe]
        if before_open_time is not None:
            clauses.append("open_time < ?")
            params.append(before_open_time)
        if closed_only:
            clauses.append("is_closed = 1")
        params.append(limit)
        sql = (
            f"SELECT {CANDLE_COLUMNS} FROM candles WHERE {' AND '.join(clauses)} "
            "ORDER BY open_time DESC LIMIT ?"
        )
        async with self.database.connection() as connection:
            cursor = await connection.execute(sql, tuple(params))
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in reversed(list(rows))]

    async def get_candles_after(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        after_open_time: int,
        limit: int,
        closed_only: bool = False,
    ) -> list[Candle]:
        """Lit les bougies strictement postérieures à un curseur."""
        closed = " AND is_closed = 1" if closed_only else ""
        sql = (
            f"SELECT {CANDLE_COLUMNS} FROM candles WHERE {MARKET_FILTER} "
            f"AND open_time > ?{closed} ORDER BY open_time ASC LIMIT ?"
        )
        params = (
            exchange_id,
            market_type,
            symbol,
            timeframe,
            after_open_time,
            limit,
        )
        async with self.database.connection() as connection:
            cursor = await connection.execute(sql, params)
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def get_window(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        anchor_open_time: int,
        before_count: int,
        after_count: int,
        closed_only: bool = False,
    ) -> list[Candle]:
        """Lit une fenêtre bornée autour d'un timestamp, sans ``OFFSET``."""
        before = await self.get_candles_before(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            before_open_time=anchor_open_time,
            limit=before_count,
            closed_only=closed_only,
        )
        after = await self.get_range(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            from_time=anchor_open_time,
            limit=after_count,
            closed_only=closed_only,
        )
        return [*before, *after]

    async def has_complete_range(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        start_time: int,
        end_time: int,
        closed_only: bool = False,
    ) -> bool:
        """Vérifie qu'une plage alignée ne contient aucun intervalle absent."""
        if start_time >= end_time:
            return True
        interval = timeframe_milliseconds(timeframe)
        expected = (end_time - start_time + interval - 1) // interval
        candles = await self.get_range(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            from_time=start_time,
            to_time=end_time,
            limit=expected + 1,
            closed_only=closed_only,
        )
        return (
            len(candles) == expected
            and candles[0].open_time == start_time
            and candles[-1].open_time == start_time + (expected - 1) * interval
        )

    async def get_history_metadata(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
    ) -> HistoryMetadata:
        """Lit la preuve du début exchange sans l'inférer depuis les bougies."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT exchange_earliest_time, exchange_earliest_verified,
                       has_more_before, last_error
                FROM candle_history_bounds
                WHERE exchange_id=? AND market_type=? AND symbol=? AND timeframe=?
                """,
                (exchange_id, market_type, symbol, timeframe),
            )
            row = await cursor.fetchone()
        if row is None:
            return HistoryMetadata()
        return HistoryMetadata(
            exchange_earliest_time=int(row[0]) if row[0] is not None else None,
            exchange_earliest_verified=bool(row[1]),
            has_more_before=bool(row[2]),
            last_error=str(row[3]) if row[3] is not None else None,
        )

    async def set_exchange_earliest_verified(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        exchange_earliest_time: int,
    ) -> None:
        """Enregistre une borne prouvée par une réponse REST partant de l'époque."""
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO candle_history_bounds (
                    exchange_id, market_type, symbol, timeframe,
                    exchange_earliest_time, exchange_earliest_verified,
                    has_more_before, last_error, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, 1,
                    CASE WHEN (
                        SELECT MIN(open_time) FROM candles
                        WHERE exchange_id=? AND market_type=? AND symbol=? AND timeframe=?
                    ) IS NULL OR (
                        SELECT MIN(open_time) FROM candles
                        WHERE exchange_id=? AND market_type=? AND symbol=? AND timeframe=?
                    ) > ? THEN 1 ELSE 0 END,
                    NULL, ?
                )
                ON CONFLICT(exchange_id, market_type, symbol, timeframe)
                DO UPDATE SET
                    exchange_earliest_time=excluded.exchange_earliest_time,
                    exchange_earliest_verified=1,
                    has_more_before=excluded.has_more_before,
                    last_error=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    exchange_earliest_time,
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    exchange_earliest_time,
                    updated_at,
                ),
            )
            await connection.commit()

    async def refresh_history_metadata(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
    ) -> HistoryMetadata:
        """Rafraîchit ``has_more_before`` sans fabriquer de borne exchange."""
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO candle_history_bounds (
                    exchange_id, market_type, symbol, timeframe,
                    exchange_earliest_time, exchange_earliest_verified,
                    has_more_before, last_error, updated_at
                ) VALUES (?, ?, ?, ?, NULL, 0, 1, NULL, ?)
                ON CONFLICT(exchange_id, market_type, symbol, timeframe)
                DO UPDATE SET
                    has_more_before=CASE
                        WHEN exchange_earliest_verified=0 THEN 1
                        WHEN exchange_earliest_time IS NULL THEN 1
                        WHEN (
                            SELECT MIN(open_time) FROM candles
                            WHERE exchange_id=? AND market_type=?
                              AND symbol=? AND timeframe=?
                        ) <= exchange_earliest_time THEN 0
                        ELSE 1
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    updated_at,
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                ),
            )
            await connection.commit()
        return await self.get_history_metadata(exchange_id, market_type, symbol, timeframe)

    async def set_history_error(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        error: str,
    ) -> None:
        """Conserve l'erreur sans transformer un échec transitoire en borne."""
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO candle_history_bounds (
                    exchange_id, market_type, symbol, timeframe,
                    exchange_earliest_time, exchange_earliest_verified,
                    has_more_before, last_error, updated_at
                ) VALUES (?, ?, ?, ?, NULL, 0, 1, ?, ?)
                ON CONFLICT(exchange_id, market_type, symbol, timeframe)
                DO UPDATE SET last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (exchange_id, market_type, symbol, timeframe, error, updated_at),
            )
            await connection.commit()

    async def clear_history_error(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        """Efface l'erreur après une tentative REST menée sans exception."""
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            await connection.execute(
                """
                UPDATE candle_history_bounds
                SET last_error=NULL, updated_at=?
                WHERE exchange_id=? AND market_type=? AND symbol=? AND timeframe=?
                """,
                (updated_at, exchange_id, market_type, symbol, timeframe),
            )
            await connection.commit()

    async def reset_history_metadata(
        self,
        *,
        exchange_id: str | None = None,
        market_type: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        only_verified: bool = True,
    ) -> int:
        """Répare une cible exacte ou toutes les bornes précédemment vérifiées."""
        target = (exchange_id, market_type, symbol, timeframe)
        if any(value is not None for value in target) and not all(
            value is not None for value in target
        ):
            raise ValueError("Une réparation ciblée exige les quatre identifiants")
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1_000)
        if all(value is not None for value in target):
            async with self.database.connection() as connection:
                await connection.execute(
                    """
                    INSERT INTO candle_history_bounds (
                        exchange_id, market_type, symbol, timeframe,
                        exchange_earliest_time, exchange_earliest_verified,
                        has_more_before, last_error, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, 0, 1, NULL, ?)
                    ON CONFLICT(exchange_id, market_type, symbol, timeframe)
                    DO UPDATE SET exchange_earliest_time=NULL,
                        exchange_earliest_verified=0, has_more_before=1,
                        last_error=NULL, updated_at=excluded.updated_at
                    """,
                    (*target, updated_at),
                )
                await connection.commit()
                return 1
        where = "WHERE exchange_earliest_verified=1" if only_verified else ""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"""
                UPDATE candle_history_bounds
                SET exchange_earliest_time=NULL,
                    exchange_earliest_verified=0,
                    has_more_before=1,
                    last_error=NULL,
                    updated_at=?
                {where}
                """,
                (updated_at,),
            )
            await connection.commit()
            return cursor.rowcount

    async def get_range(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        from_time: int | None = None,
        to_time: int | None = None,
        limit: int = 5_000,
        closed_only: bool = False,
    ) -> list[Candle]:
        """Lit une plage ``[from_time, to_time)`` bornée et chronologique."""
        clauses = [MARKET_FILTER]
        params: list[str | int] = [exchange_id, market_type, symbol, timeframe]
        if from_time is not None:
            clauses.append("open_time >= ?")
            params.append(from_time)
        if to_time is not None:
            clauses.append("open_time < ?")
            params.append(to_time)
        if closed_only:
            clauses.append("is_closed = 1")
        params.append(limit)
        sql = (
            f"SELECT {CANDLE_COLUMNS} FROM candles WHERE {' AND '.join(clauses)} "
            "ORDER BY open_time ASC LIMIT ?"
        )
        async with self.database.connection() as connection:
            cursor = await connection.execute(sql, tuple(params))
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def count(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        closed_only: bool = False,
    ) -> int:
        """Compte les bougies d'un marché."""
        closed = " AND is_closed = 1" if closed_only else ""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"SELECT COUNT(*) FROM candles WHERE {MARKET_FILTER}{closed}",
                (exchange_id, market_type, symbol, timeframe),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_first_open_time(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        closed_only: bool = False,
    ) -> int | None:
        """Retourne le premier timestamp connu."""
        return await self._time_extreme(
            "MIN", exchange_id, market_type, symbol, timeframe, closed_only=closed_only
        )

    async def get_last_open_time(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        closed_only: bool = False,
    ) -> int | None:
        """Retourne le dernier timestamp connu."""
        return await self._time_extreme(
            "MAX", exchange_id, market_type, symbol, timeframe, closed_only=closed_only
        )

    async def mark_closed(
        self, exchange_id: str, market_type: str, symbol: str, timeframe: str, open_time: int
    ) -> int:
        """Marque une bougie précise comme clôturée."""
        updated_at = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"UPDATE candles SET is_closed = 1, updated_at = ? "
                f"WHERE {MARKET_FILTER} AND open_time = ?",
                (updated_at, exchange_id, market_type, symbol, timeframe, open_time),
            )
            await connection.commit()
            return cursor.rowcount

    async def delete_open_candle(
        self, exchange_id: str, market_type: str, symbol: str, timeframe: str
    ) -> int:
        """Supprime uniquement la bougie encore ouverte d'un marché."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"DELETE FROM candles WHERE {MARKET_FILTER} AND is_closed = 0",
                (exchange_id, market_type, symbol, timeframe),
            )
            await connection.commit()
            return cursor.rowcount

    async def delete_target(
        self, exchange_id: str, market_type: str, symbol: str, timeframe: str
    ) -> int:
        """Supprime uniquement les bougies d'une cible explicitement désignée."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"DELETE FROM candles WHERE {MARKET_FILTER}",
                (exchange_id, market_type, symbol, timeframe),
            )
            await connection.commit()
        return cursor.rowcount

    async def get_candles_for_backtest(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        start_time: int,
        end_time: int,
        closed_only: bool = True,
    ) -> list[Candle]:
        """Lit localement une plage ``[start_time, end_time)`` complète."""
        coverage = await self.validate_backtest_coverage(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            closed_only=closed_only,
        )
        if not coverage.is_complete:
            raise BacktestCoverageError(
                f"Couverture incomplète pour {symbol} {timeframe}: "
                f"{coverage.candle_count}/{coverage.expected_count}"
            )
        return await self.get_range(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            from_time=start_time,
            to_time=end_time,
            limit=coverage.expected_count + 1,
            closed_only=closed_only,
        )

    async def validate_backtest_coverage(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        start_time: int,
        end_time: int,
        closed_only: bool = True,
    ) -> CoverageReport:
        """Vérifie bornes, compte et trous sans aucun accès réseau."""
        if start_time >= end_time:
            raise ValueError("start_time doit précéder end_time")
        interval = timeframe_milliseconds(timeframe)
        expected = (end_time - start_time + interval - 1) // interval
        closed = " AND is_closed=1" if closed_only else ""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"""
                SELECT MIN(open_time), MAX(open_time), COUNT(*)
                FROM candles WHERE {MARKET_FILTER}
                  AND open_time>=? AND open_time<?{closed}
                """,
                (
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    start_time,
                    end_time,
                ),
            )
            row = await cursor.fetchone()
        gaps = await self.find_missing_ranges_in_range(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            start_time=start_time,
            end_time=end_time,
            max_ranges=1_000,
            closed_only=closed_only,
        )
        count = int(row[2]) if row else 0
        available_start = int(row[0]) if row and row[0] is not None else None
        available_end = int(row[1]) if row and row[1] is not None else None
        complete = (
            count == expected
            and not gaps
            and available_start == start_time
            and available_end == end_time - interval
        )
        return CoverageReport(
            requested_start=start_time,
            requested_end=end_time,
            available_start=available_start,
            available_end=available_end,
            candle_count=count,
            expected_count=expected,
            missing_ranges=gaps,
            is_complete=complete,
        )

    async def find_missing_ranges_in_range(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        start_time: int,
        end_time: int,
        max_ranges: int = 100,
        closed_only: bool = False,
    ) -> list[tuple[int, int]]:
        """Détecte les trous internes strictement dans une plage demandée."""
        interval = timeframe_milliseconds(timeframe)
        closed = " AND is_closed=1" if closed_only else ""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"""
                SELECT previous_time + ?, open_time FROM (
                    SELECT open_time, LAG(open_time) OVER (ORDER BY open_time)
                        AS previous_time
                    FROM candles WHERE {MARKET_FILTER}
                      AND open_time>=? AND open_time<?{closed}
                ) WHERE previous_time IS NOT NULL
                    AND open_time > previous_time + ?
                ORDER BY open_time LIMIT ?
                """,
                (
                    interval,
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    start_time,
                    end_time,
                    interval,
                    max_ranges,
                ),
            )
            rows = await cursor.fetchall()
        return [(int(row[0]), int(row[1])) for row in rows]

    async def coverage_summary(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str | None = None,
        limit: int = 1_000,
    ) -> list[dict[str, Any]]:
        """Agrège la couverture locale par symbole et timeframe."""
        symbol_filter = " AND symbol=?" if symbol is not None else ""
        params: list[str | int] = [exchange_id, market_type]
        if symbol is not None:
            params.append(symbol)
        params.append(limit)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT symbol, timeframe, MIN(open_time) AS first_open_time, "
                "MAX(open_time) AS last_open_time, COUNT(*) AS candle_count, "
                "MAX(updated_at) AS last_sync_at FROM candles "
                "WHERE exchange_id=? AND market_type=?"
                f"{symbol_filter} GROUP BY symbol, timeframe "
                "ORDER BY symbol, timeframe LIMIT ?",
                tuple(params),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def has_sufficient_history(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        required_bars: int,
        *,
        closed_only: bool = True,
    ) -> bool:
        """Indique si le stockage contient le nombre minimal demandé."""
        return (
            await self.count(
                exchange_id,
                market_type,
                symbol,
                timeframe,
                closed_only=closed_only,
            )
            >= required_bars
        )

    async def find_missing_ranges(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        now_ms: int,
        max_ranges: int = 20,
    ) -> list[tuple[int, int]]:
        """Détecte des trous internes sans charger tout l'historique en mémoire."""
        interval = timeframe_milliseconds(timeframe)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"""
                SELECT previous_time + ? AS missing_from, open_time AS missing_to
                FROM (
                    SELECT
                        open_time,
                        LAG(open_time) OVER (ORDER BY open_time) AS previous_time
                    FROM candles
                    WHERE {MARKET_FILTER} AND open_time <= ?
                )
                WHERE previous_time IS NOT NULL
                  AND open_time > previous_time + ?
                ORDER BY open_time
                LIMIT ?
                """,
                (
                    interval,
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    now_ms,
                    interval,
                    max_ranges,
                ),
            )
            rows = await cursor.fetchall()
        return [(int(row[0]), int(row[1])) for row in rows]

    async def _time_extreme(
        self,
        operation: str,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        closed_only: bool,
    ) -> int | None:
        """Lit un agrégat MIN/MAX choisi exclusivement par le code."""
        closed = " AND is_closed = 1" if closed_only else ""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"SELECT {operation}(open_time) FROM candles WHERE {MARKET_FILTER}{closed}",
                (exchange_id, market_type, symbol, timeframe),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    @staticmethod
    def _from_row(row: Sequence[Any]) -> Candle:
        """Construit le modèle canonique depuis une ligne SQLite."""
        values: tuple[Any, ...] = tuple(row)
        return Candle(
            exchange_id=str(values[0]),
            market_type=str(values[1]),
            symbol=str(values[2]),
            timeframe=str(values[3]),
            open_time=int(values[4]),
            open=float(values[5]),
            high=float(values[6]),
            low=float(values[7]),
            close=float(values[8]),
            volume=float(values[9]),
            close_time=int(values[10]) if values[10] is not None else None,
            is_closed=bool(values[11]),
        )
