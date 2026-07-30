"""CLI par étape de l'expérience isolée RSI Phase 7.2."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.experiments.rsi_filter_v1 import ExperimentInvalidated, run_stage


def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    project = backend.parent
    parser = argparse.ArgumentParser(
        description="Expérience locale, déterministe et sans réseau du filtre RSI."
    )
    parser.add_argument(
        "--stage",
        required=True,
        choices=("reproduce", "development", "validation", "final-test"),
    )
    parser.add_argument("--mode", choices=("quick", "full"), default="quick")
    parser.add_argument(
        "--database",
        type=Path,
        default=backend / "data" / "scanner_crypto.sqlite3",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "docs" / "audits",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project / "docs" / "audits" / "rsi-filter-experiment-v1-plan.md",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=project / ".phase72-rsi-filter-cache.pkl.gz",
    )
    parser.add_argument(
        "--selected-variant",
        action="append",
        default=[],
        help="exactement une R1/R2/R3 pour final-test",
    )
    arguments = parser.parse_args()
    if arguments.mode == "full" and not arguments.database.is_file():
        parser.error(f"base historique introuvable: {arguments.database}")
    try:
        payload = run_stage(
            stage=arguments.stage,
            mode=arguments.mode,
            database_path=arguments.database,
            output=arguments.output,
            manifest_path=arguments.manifest,
            cache_path=arguments.cache,
            selected_variants=arguments.selected_variant,
        )
    except ExperimentInvalidated as exc:
        parser.error(f"expérience invalidée: {exc}")
    aggregate = payload.get("aggregate", {})
    variants = ",".join(payload.get("variants_executed", ["R0"]))
    print(
        f"{arguments.stage}/{arguments.mode}: variantes={variants}; "
        f"observations={sum(int(item.get('funnel', {}).get('observations', 0)) for item in aggregate.values())}; "
        f"durée={payload['duration_seconds']} s"
    )
    print(f"sortie={arguments.output.resolve()}")
    print("réseau=non; production=inchangée")


if __name__ == "__main__":
    main()
