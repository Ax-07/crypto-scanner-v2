"""Persistance du catalogue de marchés découvert par CCXT."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.database.connection import Database
from app.models.backfill import MarketRecord


class MarketRepository:
    """Conserve les marchés connus et leurs transitions d'activité."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def upsert_many(self, markets: list[MarketRecord]) -> int:
        """Met à jour atomiquement un catalogue sans perdre ``first_seen_at``."""
        if not markets:
            return 0
        now = int(datetime.now(timezone.utc).timestamp() * 1_000)
        rows = [
            (
                item.exchange_id,
                item.market_type,
                item.symbol,
                item.base,
                item.quote,
                item.exchange_market_id,
                int(item.active),
                int(item.spot),
                None if item.margin is None else int(item.margin),
                None if item.contract is None else int(item.contract),
                item.amount_precision,
                item.price_precision,
                item.min_amount,
                item.min_cost,
                now,
                now,
                None if item.active else now,
                item.raw_metadata_json,
            )
            for item in markets
        ]
        sql = """
        INSERT INTO markets (
            exchange_id, market_type, symbol, base, quote, exchange_market_id,
            active, spot, margin, contract, amount_precision, price_precision,
            min_amount, min_cost, first_seen_at, last_seen_at, deactivated_at,
            raw_metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exchange_id, market_type, symbol) DO UPDATE SET
            base=excluded.base, quote=excluded.quote,
            exchange_market_id=excluded.exchange_market_id,
            active=excluded.active, spot=excluded.spot, margin=excluded.margin,
            contract=excluded.contract, amount_precision=excluded.amount_precision,
            price_precision=excluded.price_precision, min_amount=excluded.min_amount,
            min_cost=excluded.min_cost, last_seen_at=excluded.last_seen_at,
            deactivated_at=CASE WHEN excluded.active=1 THEN NULL
                ELSE COALESCE(markets.deactivated_at, excluded.deactivated_at) END,
            raw_metadata_json=excluded.raw_metadata_json
        """
        async with self.database.connection() as connection:
            await connection.executemany(sql, rows)
            await connection.commit()
        return len(rows)

    async def mark_missing_inactive(
        self, exchange_id: str, market_type: str, seen_symbols: set[str]
    ) -> int:
        """Désactive les marchés connus absents du dernier catalogue."""
        now = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT symbol FROM markets
                WHERE exchange_id=? AND market_type=? AND active=1
                """,
                (exchange_id, market_type),
            )
            missing = [str(row[0]) for row in await cursor.fetchall() if row[0] not in seen_symbols]
            if missing:
                await connection.executemany(
                    """
                    UPDATE markets SET active=0, deactivated_at=?, last_seen_at=?
                    WHERE exchange_id=? AND market_type=? AND symbol=?
                    """,
                    [(now, now, exchange_id, market_type, symbol) for symbol in missing],
                )
                await connection.commit()
        return len(missing)

    async def list_markets(
        self,
        exchange_id: str,
        market_type: str,
        quote: str,
        *,
        include_inactive: bool = False,
    ) -> list[MarketRecord]:
        """Retourne le catalogue local filtré et trié."""
        active = "" if include_inactive else " AND active=1"
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT exchange_id, market_type, symbol, base, quote, "
                "exchange_market_id, active, spot, margin, contract, "
                "amount_precision, price_precision, min_amount, min_cost, "
                "raw_metadata_json FROM markets "
                "WHERE exchange_id=? AND market_type=? AND quote=?"
                f"{active} ORDER BY symbol",
                (exchange_id, market_type, quote),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: Any) -> MarketRecord:
        return MarketRecord(
            exchange_id=str(row[0]),
            market_type=str(row[1]),
            symbol=str(row[2]),
            base=str(row[3]),
            quote=str(row[4]),
            exchange_market_id=str(row[5]) if row[5] is not None else None,
            active=bool(row[6]),
            spot=bool(row[7]),
            margin=bool(row[8]) if row[8] is not None else None,
            contract=bool(row[9]) if row[9] is not None else None,
            amount_precision=float(row[10]) if row[10] is not None else None,
            price_precision=float(row[11]) if row[11] is not None else None,
            min_amount=float(row[12]) if row[12] is not None else None,
            min_cost=float(row[13]) if row[13] is not None else None,
            raw_metadata_json=str(row[14]) if row[14] is not None else None,
        )
