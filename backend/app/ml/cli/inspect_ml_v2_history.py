"""CLI read-only d'inventaire des historiques candidats ML v2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from app.core.config import BACKEND_ROOT, get_app_settings
from app.ml.services.ml_v2_history_inventory import inventory_ml_v2_history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventorie un historique OHLCV sans écriture.")
    parser.add_argument("symbol")
    parser.add_argument("--database-path", default=str(get_app_settings().database_path))
    parser.add_argument("--output-json", type=Path)
    return parser


def _path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        payload = inventory_ml_v2_history(_path(args.database_path), args.symbol)
        content = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        if args.output_json is not None:
            destination = _path(args.output_json)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() != content:
                raise ValueError("refus d'écraser un inventaire divergent")
            destination.write_bytes(content)
        sys.stdout.buffer.write(content)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Échec global: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
