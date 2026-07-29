"""Sauvegarde cohérente d'une base SQLite, WAL inclus."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Sequence

import aiosqlite

from app.core.config import BACKEND_ROOT, get_app_settings


async def backup(output: Path) -> None:
    """Utilise l'API SQLite backup vers un fichier distinct."""
    source = get_app_settings().database_path
    output.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(source) as source_connection:
        async with aiosqlite.connect(output) as destination:
            await source_connection.backup(destination)


def main(argv: Sequence[str] | None = None) -> int:
    """Analyse ``--output`` et exécute la sauvegarde."""
    parser = argparse.ArgumentParser(description="Sauvegarde SQLite cohérente")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if not output.is_absolute():
        output = BACKEND_ROOT / output
    if output.resolve() == get_app_settings().database_path.resolve():
        parser.error("La destination doit différer de la base source")
    asyncio.run(backup(output))
    print(f"Sauvegarde créée: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
