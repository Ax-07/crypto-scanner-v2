from __future__ import annotations

import time
import unittest
import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import scanner as scanner_api
from app.core.settings import ScanConfig
from app.main import app
from app.models.scanner import ScanJob, ScanProgress, ScanResult
from app.services.scan_manager import ScanManager


class ImmediateScanner:
    def __init__(self, config: ScanConfig) -> None:
        self.config = config
        self.partial_results: list[ScanResult] = []

    async def scan(self, update_progress):
        await update_progress(ScanProgress(total=1))
        self.partial_results.append(ScanResult(symbol="BTC/USDC", timeframe=self.config.timeframe))
        await update_progress(ScanProgress(processed=1, total=1, successful=1))
        return self.partial_results


class BlockingScanner:
    def __init__(self, _config: ScanConfig) -> None:
        self.partial_results: list[ScanResult] = []

    async def scan(self, _update_progress):
        await asyncio.Event().wait()
        return self.partial_results


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ScanManager()
        self.manager_patch = patch.object(scanner_api, "scan_manager", self.manager)
        self.scanner_patch = patch("app.services.scan_manager.ScannerService", ImmediateScanner)
        self.manager_patch.start()
        self.scanner_patch.start()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.scanner_patch.stop()
        self.manager_patch.stop()

    def create_completed_job(self) -> str:
        response = self.client.post("/api/scanner/jobs", json={"max_pairs": 1})
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["id"]
        for _ in range(50):
            if self.client.get(f"/api/scanner/jobs/{job_id}").json()["status"] == "completed":
                break
            time.sleep(0.01)
        return job_id

    def test_health_config_and_not_found(self) -> None:
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        config = self.client.get("/api/scanner/config")
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.json()["exchange_id"], "binance")
        self.assertEqual(self.client.get("/api/scanner/jobs/missing").status_code, 404)

    def test_results_too_early_and_cancellation(self) -> None:
        pending = ScanJob(id="pending", config=ScanConfig())
        self.manager._jobs[pending.id] = pending
        self.assertEqual(
            self.client.get("/api/scanner/jobs/pending/results").status_code,
            409,
        )

        with patch("app.services.scan_manager.ScannerService", BlockingScanner):
            response = self.client.post("/api/scanner/jobs", json={"max_pairs": 1})
            job_id = response.json()["id"]
            cancelled = self.client.delete(f"/api/scanner/jobs/{job_id}")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "cancelled")

    def test_create_read_results_export_and_progress_websocket(self) -> None:
        job_id = self.create_completed_job()
        job = self.client.get(f"/api/scanner/jobs/{job_id}").json()
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result_count"], 1)

        results = self.client.get(f"/api/scanner/jobs/{job_id}/results")
        self.assertEqual(results.status_code, 200)
        self.assertEqual(results.json()["results"][0]["symbol"], "BTC/USDC")
        export = self.client.get(f"/api/scanner/jobs/{job_id}/export.csv")
        self.assertEqual(export.status_code, 200)
        self.assertIn("BTC/USDC", export.text)

        with self.client.websocket_connect(f"/api/scanner/ws/{job_id}") as websocket:
            self.assertEqual(websocket.receive_json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
