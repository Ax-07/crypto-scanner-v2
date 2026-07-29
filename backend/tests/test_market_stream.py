from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from app.main import app
from app.services.market_stream import watch_ohlcv_until_disconnect


class FakeProExchange:
    def __init__(self) -> None:
        self.markets = {"BTC/USDC": {}}
        self.has = {"watchOHLCV": True}
        self.closed = False
        self.history = [
            [index * 3_600_000, 100 + index, 102 + index, 99 + index, 101 + index, 10]
            for index in range(80)
        ]
        self.watches = 0

    async def load_markets(self):
        return self.markets

    async def fetch_ohlcv(self, **_kwargs):
        return self.history

    async def watch_ohlcv(self, *_args):
        self.watches += 1
        if self.watches == 1:
            updated = list(self.history[-1])
            updated[4] += 1
            return [updated]
        if self.watches == 2:
            created = list(self.history[-1])
            created[0] += 3_600_000
            created[1] = created[2] = created[3] = created[4]
            return [created]
        raise WebSocketDisconnect()

    async def close(self):
        self.closed = True


class MarketStreamTests(unittest.TestCase):
    def test_history_open_candle_update_and_close(self) -> None:
        exchange = FakeProExchange()
        persist = AsyncMock()
        with (
            patch("app.services.market_stream.ccxtpro.binance", return_value=exchange),
            patch("app.services.market_stream._persist_stream_candle", new=persist),
            TestClient(app) as client,
            client.websocket_connect("/ws?symbol=BTC/USDC&timeframe=1h") as websocket,
        ):
            history = websocket.receive_json()
            update = websocket.receive_json()
            new_candle = websocket.receive_json()
            self.assertEqual(history["type"], "history")
            self.assertEqual(history["symbol"], "BTC/USDC")
            self.assertTrue(history["candles"])
            self.assertIn("confirmed", history["snapshot"])
            self.assertIn("provisional", history["snapshot"])
            self.assertEqual(history["snapshot"]["profile"]["origin"], "default")
            self.assertEqual(update["type"], "update")
            self.assertEqual(update["candle"]["close"], self.history_last_close(exchange) + 1)
            self.assertEqual(new_candle["type"], "update")
            self.assertGreater(new_candle["candle"]["time"], update["candle"]["time"])
        self.assertTrue(exchange.closed)
        self.assertGreaterEqual(persist.await_count, 2)

    def test_history_can_be_disabled_without_disabling_updates(self) -> None:
        exchange = FakeProExchange()
        with (
            patch("app.services.market_stream.ccxtpro.binance", return_value=exchange),
            patch("app.services.market_stream._persist_stream_candle", new=AsyncMock()),
            TestClient(app) as client,
            client.websocket_connect(
                "/ws?symbol=BTC/USDC&timeframe=1h&include_history=false"
            ) as websocket,
        ):
            first = websocket.receive_json()
            self.assertEqual(first["type"], "update")

    @staticmethod
    def history_last_close(exchange: FakeProExchange) -> float:
        return float(exchange.history[-1][4])


class BlockingExchange:
    def __init__(self) -> None:
        self.cancelled = False

    async def watch_ohlcv(self, *_args):
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True


class MarketDisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_cancels_pending_binance_watch(self) -> None:
        exchange = BlockingExchange()
        disconnect_task = asyncio.create_task(asyncio.sleep(0, result=1001))

        with self.assertRaises(WebSocketDisconnect) as raised:
            await watch_ohlcv_until_disconnect(
                exchange,
                "BTC/USDC",
                "1h",
                disconnect_task,
            )

        self.assertEqual(raised.exception.code, 1001)
        self.assertTrue(exchange.cancelled)


if __name__ == "__main__":
    unittest.main()
