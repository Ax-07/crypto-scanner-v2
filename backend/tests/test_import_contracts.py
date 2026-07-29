from __future__ import annotations

import unittest

from app.api.scanner import router
from app.domain import indicators as domain_indicators
from app.main import app, create_app
from app.services.scanner import ScannerService
from indicators import (
    calculate_bollinger_bands,
    calculate_confluence_score,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_stochastic_signal,
    detect_trend,
)
from main import app as uvicorn_app


class ImportContractTests(unittest.TestCase):
    def test_asgi_entrypoint_and_factory(self) -> None:
        self.assertIs(uvicorn_app, app)
        self.assertEqual(app.title, "Crypto Scanner & Trading Dashboard")
        self.assertEqual(create_app().title, app.title)

    def test_scanner_service_and_router_are_importable(self) -> None:
        self.assertTrue(callable(ScannerService))
        self.assertEqual(router.prefix, "/api/scanner")

    def test_historical_indicator_module_is_only_compatibility_exports(self) -> None:
        exported = (
            calculate_rsi,
            calculate_sma,
            calculate_ema,
            detect_trend,
            calculate_macd,
            detect_macd_signal,
            calculate_bollinger_bands,
            detect_bollinger_signal,
            calculate_stochastic,
            detect_stochastic_signal,
            calculate_confluence_score,
        )
        for function in exported:
            with self.subTest(function=function.__name__):
                self.assertIs(function, getattr(domain_indicators, function.__name__))

    def test_all_public_routes_are_registered(self) -> None:
        paths = {route.path for route in (*app.routes, *router.routes) if hasattr(route, "path")}
        self.assertTrue(
            {
                "/api/scanner/config",
                "/api/scanner/markets",
                "/api/scanner/jobs",
                "/api/scanner/jobs/{job_id}",
                "/api/scanner/jobs/{job_id}/results",
                "/api/scanner/jobs/{job_id}/export.csv",
                "/api/scanner/ws/{job_id}",
                "/api/health",
                "/health",
                "/ws",
            }.issubset(paths)
        )

    def test_openapi_documents_scanner_routes_and_config(self) -> None:
        schema = app.openapi()
        self.assertEqual(
            schema["paths"]["/api/scanner/jobs"]["post"]["summary"],
            "Démarrer un scan de marché",
        )
        self.assertEqual(
            schema["paths"]["/api/scanner/jobs/{job_id}/results"]["get"]["responses"]["409"][
                "description"
            ],
            "Scan encore en cours ou en échec",
        )
        scan_config = schema["components"]["schemas"]["ScanConfig"]
        self.assertIn("configuration", scan_config["description"].lower())
        self.assertEqual(
            scan_config["properties"]["retry_delay_seconds"]["description"],
            "Délai initial du backoff, en secondes.",
        )


if __name__ == "__main__":
    unittest.main()
