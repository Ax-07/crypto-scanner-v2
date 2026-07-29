from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import ccxt.async_support as ccxt

from app.core.settings import ScanConfig
from app.services.market_data import fetch_ohlcv


def config(**changes: object) -> ScanConfig:
    values: dict[str, object] = {
        "use_rsi": False,
        "use_ma": False,
        "use_macd": False,
        "use_bollinger": False,
        "use_stochastic": False,
        "use_confluence_score": False,
        "min_ohlcv_bars": 60,
        "retry_delay_seconds": 0.1,
    }
    values.update(changes)
    return ScanConfig(**values)


class MarketDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_success(self) -> None:
        exchange = AsyncMock()
        exchange.fetch_ohlcv.return_value = [[0, 1, 2, 0.5, 1.5, 10]]
        frame = await fetch_ohlcv(exchange, "BTC/USDC", "4h", 10, config())
        self.assertIsNotNone(frame)
        self.assertEqual(float(frame.iloc[0]["close"]), 1.5)

    async def test_network_error_retries_then_succeeds(self) -> None:
        exchange = AsyncMock()
        exchange.fetch_ohlcv.side_effect = [
            ccxt.NetworkError("temporary"),
            [[0, 1, 2, 0.5, 1.5, 10]],
        ]
        with patch("app.services.market_data.asyncio.sleep", new=AsyncMock()) as sleep:
            frame = await fetch_ohlcv(exchange, "BTC/USDC", "4h", 10, config(max_retries=2))
        self.assertIsNotNone(frame)
        self.assertEqual(exchange.fetch_ohlcv.await_count, 2)
        sleep.assert_awaited_once()

    async def test_retry_limit_and_definitive_error(self) -> None:
        exchange = AsyncMock()
        exchange.fetch_ohlcv.side_effect = ccxt.NetworkError("offline")
        with patch("app.services.market_data.asyncio.sleep", new=AsyncMock()):
            result = await fetch_ohlcv(exchange, "BTC/USDC", "4h", 10, config(max_retries=2))
        self.assertIsNone(result)
        self.assertEqual(exchange.fetch_ohlcv.await_count, 3)

        exchange.fetch_ohlcv.reset_mock(side_effect=True)
        exchange.fetch_ohlcv.side_effect = ccxt.BadSymbol("bad")
        result = await fetch_ohlcv(exchange, "BAD/USDC", "4h", 10, config(max_retries=8))
        self.assertIsNone(result)
        self.assertEqual(exchange.fetch_ohlcv.await_count, 1)


if __name__ == "__main__":
    unittest.main()
