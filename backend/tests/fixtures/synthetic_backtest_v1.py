"""Jeu OHLCV synthétique v1, déterministe et sans dépendance réseau."""

from __future__ import annotations

import math

from app.domain.candles import Candle

DATASET_VERSION = "synthetic-backtest-v1"
START_MS = 1_700_000_000_000
INTERVAL_MS = 60_000


def candles(count: int = 140, symbol: str = "SYN/USDC") -> list[Candle]:
    result = []
    previous = 100.0
    for index in range(count):
        close = 100 + index * 0.035 + math.sin(index / 4) * 3 + math.sin(index / 11)
        open_price = previous
        result.append(
            Candle(
                exchange_id="binance",
                market_type="spot",
                symbol=symbol,
                timeframe="1m",
                open_time=START_MS + index * INTERVAL_MS,
                open=open_price,
                high=max(open_price, close) + 0.4,
                low=min(open_price, close) - 0.4,
                close=close,
                volume=1_000 + index,
                close_time=START_MS + (index + 1) * INTERVAL_MS,
                is_closed=True,
            )
        )
        previous = close
    return result
