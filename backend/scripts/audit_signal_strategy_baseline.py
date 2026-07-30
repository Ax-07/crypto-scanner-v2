"""CLI reproductible de la baseline signaux/stratégie v1."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audits.signal_strategy_baseline import run_sync, write_outputs


def _git_head(project_root: Path) -> str:
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={project_root.as_posix()}",
            "rev-parse",
            "--short",
            "HEAD",
        ],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _generated_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--generated-at doit inclure un fuseau")
    return parsed.astimezone(timezone.utc)


def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    project = backend.parent
    parser = argparse.ArgumentParser(
        description="Mesure locale, déterministe et sans réseau de la stratégie actuelle."
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
        "--generated-at",
        help="timestamp ISO injecté pour une reproduction octet-à-octet",
    )
    arguments = parser.parse_args()
    if not arguments.database.is_file():
        parser.error(f"base historique introuvable: {arguments.database}")
    generated_at = _generated_at(arguments.generated_at)
    payload = run_sync(
        database_path=arguments.database,
        mode=arguments.mode,
        generated_at=generated_at,
        git_head=_git_head(project),
    )
    markdown, summary = write_outputs(payload, arguments.output)
    aggregate = payload.get("aggregate_metrics", {})
    print(
        f"{arguments.mode}: {len(payload.get('selected', []))} combinaison(s), "
        f"{aggregate.get('observation_count', 0)} observations, "
        f"{aggregate.get('trade_count', 0)} trades, "
        f"{payload['duration_seconds']} s"
    )
    print(markdown)
    print(summary)
    print("réseau=non; base_historique=lecture_seule; temporaires=nettoyés")


if __name__ == "__main__":
    main()
