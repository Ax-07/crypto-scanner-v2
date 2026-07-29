from __future__ import annotations

import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.domain.candles import Candle
from app.main import create_app
from app.models.backfill import BackfillStatus, SyncState
from app.services.market_history import MarketHistoryResult


class CandlesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "api.sqlite3"
        self.environment = patch.dict("os.environ", {"DATABASE_PATH": str(self.database_path)})
        self.environment.start()
        self.context = TestClient(create_app())
        self.client = self.context.__enter__()
        repository = self.client.app.state.candle_repository
        self.client.portal.call(
            repository.upsert_many,
            [
                Candle(
                    "binance",
                    "spot",
                    "BTC/USDC",
                    "1h",
                    timestamp,
                    1,
                    2,
                    0.5,
                    1.5,
                    10,
                    timestamp + 3_600_000,
                    closed,
                )
                for timestamp, closed in ((0, True), (3_600_000, False))
            ],
        )
        self.client.portal.call(
            self.client.app.state.backfill_repository.save_state,
            SyncState(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1h",
                status=BackfillStatus.COMPLETED,
            ),
        )

    def tearDown(self) -> None:
        self.context.__exit__(None, None, None)
        self.environment.stop()
        self.temporary.cleanup()

    def test_get_order_filters_empty_and_validation(self) -> None:
        response = self.client.get(
            "/api/market/candles",
            params={"symbol": "BTC/USDC", "timeframe": "1h", "limit": 10},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["time"] for item in response.json()["candles"]],
            [0, 3600],
        )
        payload = response.json()
        self.assertEqual(payload["page"]["count"], 2)
        self.assertEqual(payload["page"]["oldest_open_time"], 0)
        self.assertEqual(payload["coverage"]["total_candles"], 2)
        self.assertFalse(payload["coverage"]["is_complete"])
        self.assertFalse(payload["coverage"]["is_earliest_known"])
        self.assertIn("source", payload)
        self.assertEqual(payload["candles"][0]["open_time"], 0)
        self.assertTrue(payload["candles"][0]["is_closed"])
        self.assertIn("indicators", payload)
        self.assertIn("markers", payload)
        self.assertIn("snapshot", payload)
        self.assertIn("confirmed", payload["snapshot"])
        self.assertEqual(payload["profile"]["origin"], "default")
        closed = self.client.get(
            "/api/market/candles",
            params={
                "symbol": "BTC/USDC",
                "timeframe": "1h",
                "closed_only": True,
            },
        )
        self.assertEqual(len(closed.json()["candles"]), 1)
        empty = self.client.get(
            "/api/market/candles",
            params={"symbol": "ETH/USDC", "timeframe": "1h"},
        )
        self.assertEqual(empty.json()["candles"], [])
        self.assertEqual(empty.json()["page"]["count"], 0)
        self.assertIsNone(empty.json()["page"]["next_before"])
        self.assertEqual(empty.json()["coverage"]["total_candles"], 0)
        self.assertEqual(
            self.client.get(
                "/api/market/candles",
                params={"symbol": "../bad", "timeframe": "1h"},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/market/candles",
                params={"symbol": "BTC/USDC", "timeframe": "10m"},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/market/candles",
                params={
                    "symbol": "BTC/USDC",
                    "timeframe": "1h",
                    "from_time": 10,
                    "to_time": 5,
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/market/candles",
                params={"symbol": "BTC/USDC", "limit": 5001},
            ).status_code,
            422,
        )
        exclusive = self.client.get(
            "/api/market/candles",
            params={"symbol": "BTC/USDC", "before": 3_600_000, "limit": 10},
        )
        self.assertEqual([item["open_time"] for item in exclusive.json()["candles"]], [0])
        self.assertTrue(exclusive.json()["page"]["has_more_before"])
        repository = self.client.app.state.candle_repository
        self.client.portal.call(
            repository.set_exchange_earliest_verified,
            "binance",
            "spot",
            "BTC/USDC",
            "1h",
            0,
        )
        verified = self.client.get(
            "/api/market/candles",
            params={"symbol": "BTC/USDC", "timeframe": "1h", "limit": 10},
        ).json()
        self.assertEqual(verified["coverage"]["local_earliest_time"], 0)
        self.assertEqual(verified["coverage"]["exchange_earliest_time"], 0)
        self.assertTrue(verified["coverage"]["exchange_earliest_verified"])
        self.assertFalse(verified["page"]["has_more_before"])
        self.assertEqual(
            self.client.get(
                "/api/market/candles",
                params={"symbol": "BTC/USDC", "before": 1, "after": 2},
            ).status_code,
            422,
        )

    def test_status_and_csv_export(self) -> None:
        status = self.client.get(
            "/api/market/candles/status",
            params={"symbol": "BTC/USDC", "timeframe": "1h"},
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["count"], 2)
        self.assertEqual(status.json()["last_closed_open_time"], 0)
        exported = self.client.get(
            "/api/market/candles/export.csv",
            params={"symbol": "BTC/USDC", "timeframe": "1h"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("open_time,open,high", exported.text)
        self.assertIn("BTC-USDC-1h.csv", exported.headers["content-disposition"])

    def test_date_window_route_returns_cursor_metadata_without_live_exchange(self) -> None:
        repository = self.client.app.state.candle_repository
        candles = self.client.portal.call(
            partial(
                repository.get_latest,
                closed_only=False,
            ),
            "binance",
            "spot",
            "BTC/USDC",
            "1h",
            10,
        )
        result = MarketHistoryResult(
            candles=candles,
            downloaded_from_exchange=2,
            local_earliest_time=0,
            exchange_earliest_time=None,
            exchange_earliest_verified=False,
            has_more_before=True,
            history_last_error=None,
            latest_available=3_600_000,
            local_candle_count=2,
            recent_complete=False,
        )
        loader = AsyncMock(return_value=result)
        with patch.object(self.client.app.state.market_history, "get_around", loader):
            response = self.client.get(
                "/api/market/candles/window",
                params={
                    "symbol": "BTC/USDC",
                    "timeframe": "1h",
                    "anchor_time": 3_600_000,
                    "before_count": 1,
                    "after_count": 1,
                },
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["anchor_time"], 3_600_000)
        self.assertEqual(payload["source"]["downloaded_from_exchange"], 2)
        self.assertEqual(payload["page"]["next_before"], 0)
        self.assertEqual(payload["page"]["next_after"], 3_600_000)
        loader.assert_awaited_once()

    def test_history_coverage_runs_and_validation(self) -> None:
        coverage = self.client.get("/api/market/history/coverage")
        self.assertEqual(coverage.status_code, 200)
        self.assertEqual(coverage.json()["coverage"][0]["status"], "completed")
        symbol = self.client.get("/api/market/history/coverage/BTC%2FUSDC")
        self.assertEqual(symbol.status_code, 200)
        self.assertEqual(symbol.json()["symbol"], "BTC/USDC")
        self.assertEqual(self.client.get("/api/market/history/coverage/bad").status_code, 422)
        self.assertEqual(self.client.get("/api/market/history/runs").json(), [])
        self.assertEqual(
            self.client.get(
                "/api/market/history/runs/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/market/history/runs/not-an-id").status_code, 422)


if __name__ == "__main__":
    unittest.main()
