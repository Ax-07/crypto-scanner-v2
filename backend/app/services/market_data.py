"""Récupération résiliente et lecture des bougies OHLCV du scanner."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import ccxt.async_support as ccxt
import pandas as pd

from app.core.settings import ScanConfig
from app.domain.candles import candles_to_frame, closed_candles, rows_to_frame
from app.services.candle_sync import CandleSyncService

logger = logging.getLogger(__name__)


async def fetch_ohlcv(
    exchange: Any,
    symbol: str,
    timeframe: str,
    limit: int,
    config: ScanConfig,
    candle_sync: CandleSyncService | None = None,
) -> pd.DataFrame | None:
    """Récupère et normalise des bougies avec retry des erreurs transitoires.

    Les erreurs réseau et de rate limit sont retentées avec backoff exponentiel,
    jitter de 0,9 à 1,1 et plafond de 30 secondes. Une ``ExchangeError`` est
    définitive. La fonction retourne ``None`` après abandon ou données vides.

    Cette coroutine est annulable pendant l'appel CCXT ou le délai de backoff.
    """
    if candle_sync is not None and candle_sync.settings.candle_storage_enabled:
        try:
            candles = await candle_sync.ensure_history(
                exchange_id=config.exchange_id,
                market_type=config.market_type,
                symbol=symbol,
                timeframe=timeframe,
                required_bars=max(1, limit - 1),
                closed_only=True,
                exchange=exchange,
                max_retries=config.max_retries,
                retry_delay_seconds=config.retry_delay_seconds,
            )
            frame = candles_to_frame(candles)
            return frame if not frame.empty else None
        except Exception as exc:
            logger.warning("Historique local indisponible pour %s %s: %s", symbol, timeframe, exc)
            return None

    delay = config.retry_delay_seconds
    for attempt in range(config.max_retries + 1):
        try:
            rows = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not rows:
                return None
            frame = rows_to_frame(rows)
            return frame if not frame.empty else None
        except (ccxt.RateLimitExceeded, ccxt.NetworkError) as exc:
            if attempt >= config.max_retries:
                logger.warning(
                    "OHLCV abandonné pour %s après %s tentative(s): %s",
                    symbol,
                    attempt + 1,
                    exc,
                )
                return None
            await asyncio.sleep(min(delay, 30.0) * random.uniform(0.9, 1.1))
            delay = min(delay * 2, 30.0)
        except ccxt.ExchangeError as exc:
            logger.warning("Erreur exchange définitive pour %s: %s", symbol, exc)
            return None
    return None


def get_closed_candles(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Filtre un DataFrame pour ne conserver que les bougies clôturées."""
    return closed_candles(frame, timeframe)


def get_last_closed_candle(frame: pd.DataFrame, timeframe: str) -> dict[str, Any] | None:
    """Retourne la dernière bougie clôturée avec une date UTC et des floats."""
    if frame is None or frame.empty:
        return None

    closed = get_closed_candles(frame, timeframe)
    if closed.empty:
        return None

    row = closed.iloc[-1]
    return {
        "time": row["time"].to_pydatetime(),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
    }
