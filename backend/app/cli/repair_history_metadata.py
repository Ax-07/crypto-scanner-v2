"""Réinitialise les bornes historiques exchange sans supprimer de bougies."""

from __future__ import annotations

import argparse
import asyncio
from typing import Sequence

from app.core.config import get_app_settings
from app.database.connection import Database
from app.repositories.candle_repository import CandleRepository


async def repair(
    *,
    exchange_id: str | None = None,
    market_type: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    all_targets: bool = False,
) -> int:
    """Répare une cible exacte ou toutes celles déclarées vérifiées."""
    database = Database(get_app_settings().database_path)
    await database.initialize()
    try:
        repository = CandleRepository(database)
        return await repository.reset_history_metadata(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            only_verified=not all_targets,
        )
    finally:
        await database.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Répare les métadonnées de début historique OHLCV")
    parser.add_argument("--exchange-id")
    parser.add_argument("--market-type")
    parser.add_argument("--symbol")
    parser.add_argument("--timeframe")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Réinitialise toutes les cibles, pas seulement celles vérifiées",
    )
    args = parser.parse_args(argv)
    target_values = (
        args.exchange_id,
        args.market_type,
        args.symbol,
        args.timeframe,
    )
    if any(target_values) and not all(target_values):
        parser.error("Une cible exige --exchange-id, --market-type, --symbol et --timeframe")
    count = asyncio.run(
        repair(
            exchange_id=args.exchange_id.lower() if args.exchange_id else None,
            market_type=args.market_type.lower() if args.market_type else None,
            symbol=args.symbol.upper() if args.symbol else None,
            timeframe=args.timeframe,
            all_targets=args.all,
        )
    )
    print(f"Métadonnées réparées : {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
