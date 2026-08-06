"""Inventaire déterministe et strictement read-only de l'historique ML v2."""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.candles import timeframe_milliseconds

HISTORY_INVENTORY_VERSION = "ml-v2-history-inventory-v1"


def _iso(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return (
        datetime.fromtimestamp(timestamp_ms / 1_000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def inventory_ml_v2_history(database_path: Path, symbol: str) -> dict[str, Any]:
    """Inspecte les bougies sans migration, WAL ou écriture implicite."""
    path = Path(database_path).resolve()
    if not path.is_file():
        raise ValueError("la base SQLite candidate est introuvable")
    normalized_symbol = symbol.strip().upper()
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        schema_row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()
        rows = connection.execute(
            """
            SELECT exchange_id, market_type, symbol, timeframe, open_time,
                   open, high, low, close, volume, close_time, is_closed
            FROM candles WHERE symbol=?
            ORDER BY exchange_id, market_type, timeframe, open_time
            """,
            (normalized_symbol,),
        ).fetchall()
        if not rows:
            raise ValueError(f"aucune bougie trouvée pour {normalized_symbol}")

        grouped: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(
                (str(row["exchange_id"]), str(row["market_type"]), str(row["timeframe"])),
                [],
            ).append(row)

        streams: list[dict[str, Any]] = []
        for (exchange_id, market_type, timeframe), items in sorted(grouped.items()):
            interval = timeframe_milliseconds(timeframe)
            gaps: list[list[int]] = []
            duplicates = 0
            non_monotone = 0
            previous: int | None = None
            years: Counter[str] = Counter()
            non_finite = negative = inconsistent = open_count = 0
            for item in items:
                timestamp = int(item["open_time"])
                years[str(datetime.fromtimestamp(timestamp / 1_000, timezone.utc).year)] += 1
                if previous is not None:
                    if timestamp == previous:
                        duplicates += 1
                    elif timestamp < previous:
                        non_monotone += 1
                    elif timestamp - previous != interval:
                        gaps.append([previous + interval, timestamp])
                numbers = [float(item[name]) for name in ("open", "high", "low", "close", "volume")]
                non_finite += int(not all(math.isfinite(value) for value in numbers))
                negative += int(any(value < 0 for value in numbers))
                inconsistent += int(
                    numbers[1] < numbers[2]
                    or not numbers[2] <= numbers[0] <= numbers[1]
                    or not numbers[2] <= numbers[3] <= numbers[1]
                )
                open_count += int(not bool(item["is_closed"]))
                previous = timestamp
            streams.append(
                {
                    "exchange_id": exchange_id,
                    "market_type": market_type,
                    "symbol": normalized_symbol,
                    "timeframe": timeframe,
                    "candle_count": len(items),
                    "first_open_time": _iso(int(items[0]["open_time"])),
                    "last_open_time": _iso(int(items[-1]["open_time"])),
                    "first_open_time_ms": int(items[0]["open_time"]),
                    "last_open_time_ms": int(items[-1]["open_time"]),
                    "gap_count": len(gaps),
                    "gap_examples_ms": gaps[:20],
                    "duplicate_count": duplicates,
                    "non_monotone_count": non_monotone,
                    "open_candle_count": open_count,
                    "non_finite_count": non_finite,
                    "negative_ohlcv_count": negative,
                    "inconsistent_ohlc_count": inconsistent,
                    "candles_by_year": dict(sorted(years.items())),
                }
            )
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        return {
            "inventory_version": HISTORY_INVENTORY_VERSION,
            "schema_version": int(schema_row[0]) if schema_row else 0,
            "symbol": normalized_symbol,
            "integrity_check": integrity,
            "foreign_key_violation_count": foreign_keys,
            "streams": streams,
        }
    finally:
        connection.close()
