from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.ml.cli.export_ml_dataset import (
    build_parser,
    main,
    options_from_args,
    run_cli,
)
from app.core.config import BACKEND_ROOT
from app.ml.models.ml_dataset_export import (
    MLDatasetExportManifest,
    MLDatasetExportStats,
)
from app.ml.services.ml_dataset_builder import (
    MLDatasetBuildReport,
    MLDatasetBuildResult,
)
from app.ml.services.ml_dataset_exporter import (
    MLDatasetExportResult,
)

EMPTY_SHA256 = "sha256:" "e3b0c44298fc1c149afbf4c8996fb924" "27ae41e4649b934ca495991b7852b855"


def empty_build_result(
    *,
    job_id: str = "job-1",
    natr_multiplier: float = 1.25,
) -> MLDatasetBuildResult:
    """Construit un résultat de génération vide et cohérent."""
    report = MLDatasetBuildReport(
        source_rows=0,
        processed_rows=0,
        generated_rows=0,
        skipped_rows=0,
        censored_outcomes=0,
        invalid_outcomes=0,
        missing_natr=0,
        contract_rejections=0,
        batch_count=0,
        rejection_reasons={},
    )

    return MLDatasetBuildResult(
        job_id=job_id,
        horizon=6,
        natr_multiplier=natr_multiplier,
        rows=(),
        report=report,
    )


def empty_export_result(
    output_directory: Path,
    *,
    job_id: str = "job-1",
    natr_multiplier: float = 1.25,
) -> MLDatasetExportResult:
    """Construit un résultat d'export vide et cohérent."""
    stats = MLDatasetExportStats(
        source_rows=0,
        processed_rows=0,
        generated_rows=0,
        skipped_rows=0,
        censored_outcomes=0,
        invalid_outcomes=0,
        missing_natr=0,
        contract_rejections=0,
        batch_count=0,
        rejection_reasons={},
    )

    manifest = MLDatasetExportManifest(
        source_job_id=job_id,
        horizon=6,
        natr_multiplier=natr_multiplier,
        data_file="custom.jsonl",
        data_sha256=EMPTY_SHA256,
        row_count=0,
        first_decision_time=None,
        last_decision_time=None,
        feature_names=[],
        stats=stats,
    )

    return MLDatasetExportResult(
        data_path=output_directory / "custom.jsonl",
        manifest_path=(output_directory / "custom.manifest.json"),
        manifest=manifest,
    )


class ExportMLDatasetCliOptionTests(unittest.TestCase):
    def test_options_are_validated_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "source.sqlite3"
            database_path.write_bytes(b"")

            parser = build_parser()
            options = options_from_args(
                parser.parse_args(
                    [
                        " job-1 ",
                        "--database-path",
                        str(database_path),
                        "--output-directory",
                        "artifacts/test-ml",
                        "--batch-size",
                        "250",
                        "--natr-multiplier",
                        "1.5",
                        "--file-stem",
                        " custom-export ",
                    ]
                )
            )

            self.assertEqual(
                options.job_id,
                "job-1",
            )
            self.assertEqual(
                options.database_path,
                database_path,
            )
            self.assertEqual(
                options.output_directory,
                BACKEND_ROOT / "artifacts/test-ml",
            )
            self.assertEqual(
                options.batch_size,
                250,
            )
            self.assertEqual(
                options.natr_multiplier,
                1.5,
            )
            self.assertEqual(
                options.file_stem,
                "custom-export",
            )

    def test_missing_database_is_rejected(self) -> None:
        parser = build_parser()

        with tempfile.TemporaryDirectory() as temporary:
            missing_path = Path(temporary) / "missing.sqlite3"

            with self.assertRaisesRegex(
                ValueError,
                "introuvable",
            ):
                options_from_args(
                    parser.parse_args(
                        [
                            "job-1",
                            "--database-path",
                            str(missing_path),
                        ]
                    )
                )

    def test_invalid_batch_size_returns_code_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "source.sqlite3"
            database_path.write_bytes(b"")

            with patch(
                "sys.stderr",
                new_callable=io.StringIO,
            ) as stderr:
                exit_code = main(
                    [
                        "job-1",
                        "--database-path",
                        str(database_path),
                        "--batch-size",
                        "0",
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn(
                "--batch-size",
                stderr.getvalue(),
            )

    def test_main_returns_one_on_unexpected_failure(self) -> None:
        failing_run = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch(
                "app.ml.cli.export_ml_dataset.run_cli",
                new=failing_run,
            ),
            patch(
                "sys.stderr",
                new_callable=io.StringIO,
            ) as stderr,
        ):
            exit_code = main(["job-1"])

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "RuntimeError: boom",
            stderr.getvalue(),
        )

    def test_main_returns_130_on_keyboard_interrupt(self) -> None:
        interrupted_run = AsyncMock(side_effect=KeyboardInterrupt)

        with (
            patch(
                "app.ml.cli.export_ml_dataset.run_cli",
                new=interrupted_run,
            ),
            patch(
                "sys.stderr",
                new_callable=io.StringIO,
            ) as stderr,
        ):
            exit_code = main(["job-1"])

        self.assertEqual(exit_code, 130)
        self.assertIn(
            "Export interrompu",
            stderr.getvalue(),
        )


class ExportMLDatasetCliAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_cli_builds_exports_prints_and_closes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database_path = root / "source.sqlite3"
            output_directory = root / "exports"
            database_path.write_bytes(b"")

            args = build_parser().parse_args(
                [
                    "job-1",
                    "--database-path",
                    str(database_path),
                    "--output-directory",
                    str(output_directory),
                    "--batch-size",
                    "50",
                    "--natr-multiplier",
                    "1.25",
                    "--file-stem",
                    "custom",
                ]
            )

            build_result = empty_build_result()
            export_result = empty_export_result(output_directory)

            database = MagicMock()
            database.initialize = AsyncMock()
            database.close = AsyncMock()

            repository = MagicMock()

            builder = MagicMock()
            builder.build = AsyncMock(return_value=build_result)

            exporter = MagicMock()
            exporter.export.return_value = export_result

            with (
                patch("app.ml.cli.export_ml_dataset.configure_logging"),
                patch(
                    "app.ml.cli.export_ml_dataset.Database",
                    return_value=database,
                ) as database_class,
                patch(
                    "app.ml.cli.export_ml_dataset.BacktestRepository",
                    return_value=repository,
                ) as repository_class,
                patch(
                    "app.ml.cli.export_ml_dataset.MLDatasetBuilder",
                    return_value=builder,
                ) as builder_class,
                patch(
                    "app.ml.cli.export_ml_dataset.MLDatasetExporter",
                    return_value=exporter,
                ) as exporter_class,
                patch(
                    "sys.stdout",
                    new_callable=io.StringIO,
                ) as stdout,
            ):
                exit_code = await run_cli(args)

            self.assertEqual(exit_code, 0)

            database_class.assert_called_once_with(database_path)
            database.initialize.assert_awaited_once_with()

            repository_class.assert_called_once_with(database)
            builder_class.assert_called_once_with(repository)
            builder.build.assert_awaited_once_with(
                "job-1",
                batch_size=50,
                natr_multiplier=1.25,
            )

            exporter_class.assert_called_once_with()
            exporter.export.assert_called_once_with(
                build_result,
                output_directory,
                file_stem="custom",
            )

            database.close.assert_awaited_once_with()

            payload = json.loads(stdout.getvalue())

            self.assertEqual(
                payload["source_job_id"],
                "job-1",
            )
            self.assertEqual(
                payload["horizon"],
                6,
            )
            self.assertEqual(
                payload["natr_multiplier"],
                1.25,
            )
            self.assertEqual(
                payload["row_count"],
                0,
            )
            self.assertEqual(
                payload["feature_count"],
                0,
            )
            self.assertEqual(
                payload["data_sha256"],
                EMPTY_SHA256,
            )
            self.assertEqual(
                payload["data_path"],
                str(export_result.data_path),
            )
            self.assertEqual(
                payload["manifest_path"],
                str(export_result.manifest_path),
            )

    async def test_run_cli_closes_database_when_builder_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "source.sqlite3"
            database_path.write_bytes(b"")

            args = build_parser().parse_args(
                [
                    "job-1",
                    "--database-path",
                    str(database_path),
                ]
            )

            database = MagicMock()
            database.initialize = AsyncMock()
            database.close = AsyncMock()

            builder = MagicMock()
            builder.build = AsyncMock(side_effect=RuntimeError("builder failure"))

            with (
                patch("app.ml.cli.export_ml_dataset.configure_logging"),
                patch(
                    "app.ml.cli.export_ml_dataset.Database",
                    return_value=database,
                ),
                patch(
                    "app.ml.cli.export_ml_dataset.BacktestRepository",
                    return_value=MagicMock(),
                ),
                patch(
                    "app.ml.cli.export_ml_dataset.MLDatasetBuilder",
                    return_value=builder,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "builder failure",
                ):
                    await run_cli(args)

            database.initialize.assert_awaited_once_with()
            database.close.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
