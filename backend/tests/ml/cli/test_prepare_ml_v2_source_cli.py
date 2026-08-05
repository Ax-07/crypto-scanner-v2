from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.ml.cli.prepare_ml_v2_source import build_parser, main, run_cli
from app.ml.services.ml_v2_source import (
    MLV2SourceResult,
    build_ml_v2_source_config,
    ml_v2_source_identity,
)
from app.domain.backtesting import signal_profile_fingerprint


class PrepareMLV2SourceCliTests(unittest.TestCase):
    def test_parser_does_not_expose_canonical_profile_overrides(self) -> None:
        destinations = {action.dest for action in build_parser()._actions}
        forbidden = {
            "signal_profile_id",
            "horizons",
            "replay_mode",
            "entry_policy",
            "gap_policy",
            "snapshot_status",
            "signal_config",
        }
        self.assertTrue(forbidden.isdisjoint(destinations))

    def test_invalid_or_naive_dates_return_nonzero(self) -> None:
        common = ["SYN/USDC", "--timeframe", "1m", "--end", "2024-01-02T00:00:00Z"]
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main([*common, "--start", "invalid"]), 2)
            self.assertEqual(main([*common, "--start", "2024-01-01T00:00:00"]), 2)


class PrepareMLV2SourceCliAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_is_read_only_and_json_uses_structured_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "existing.sqlite3"
            database_path.write_bytes(b"sqlite-placeholder")
            args = build_parser().parse_args(
                [
                    "SYN/USDC",
                    "--timeframe",
                    "1m",
                    "--start",
                    "2024-01-01T00:00:00Z",
                    "--end",
                    "2024-01-02T00:00:00Z",
                    "--database-path",
                    str(database_path),
                    "--dry-run",
                    "--json",
                ]
            )
            config = build_ml_v2_source_config(
                symbol="SYN/USDC",
                timeframe="1m",
                start=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
                end=datetime.fromisoformat("2024-01-02T00:00:00+00:00"),
            )
            result = MLV2SourceResult(
                action="would-create",
                reason="aucun source compatible existant",
                config=config,
                source_identity=ml_v2_source_identity(config),
                profile_fingerprint=signal_profile_fingerprint(config.signal_config),
                job=None,
                coverage=(),
                dry_run=True,
            )
            database = MagicMock()
            database.initialize = AsyncMock()
            database.close = AsyncMock()
            service = MagicMock()
            service.prepare = AsyncMock(return_value=result)

            with (
                patch("app.ml.cli.prepare_ml_v2_source.configure_logging"),
                patch("app.ml.cli.prepare_ml_v2_source.Database", return_value=database),
                patch(
                    "app.ml.cli.prepare_ml_v2_source.BacktestRepository",
                    return_value=MagicMock(),
                ),
                patch(
                    "app.ml.cli.prepare_ml_v2_source.CandleRepository",
                    return_value=MagicMock(),
                ),
                patch(
                    "app.ml.cli.prepare_ml_v2_source.BacktestManager",
                    return_value=MagicMock(),
                ),
                patch(
                    "app.ml.cli.prepare_ml_v2_source.MLV2SourceService",
                    return_value=service,
                ),
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = await run_cli(args)

            self.assertEqual(exit_code, 0)
            database.initialize.assert_not_awaited()
            database.close.assert_awaited_once_with()
            service.prepare.assert_awaited_once()
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["action"], "would-create")
            self.assertEqual(payload["signal_profile_id"], "ml-dataset-v2")
            self.assertEqual(payload["feature_schema_version"], "causal-features-v2")
            self.assertIsNone(payload["fingerprints"]["config_fingerprint"])


if __name__ == "__main__":
    unittest.main()
