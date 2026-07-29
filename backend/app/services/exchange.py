"""Adaptateur minimal entre la configuration du scanner et CCXT async."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import ccxt.async_support as ccxt

from app.core.settings import ScanConfig
from app.core.exceptions import UnknownExchangeError

logger = logging.getLogger(__name__)

STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "EURC"}


class ExchangeProtocol(Protocol):
    """Surface CCXT requise par les services, utile aux faux exchanges de test."""

    markets: dict[str, dict[str, Any]]
    timeframes: dict[str, str]
    has: dict[str, Any]

    async def load_markets(self) -> dict[str, dict[str, Any]]:
        """Charge et retourne les métadonnées des marchés."""
        ...

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        since: int | None = None,
    ) -> list[list[Any]]:
        """Récupère au plus ``limit`` lignes OHLCV au format CCXT."""
        ...

    async def close(self) -> None:
        """Ferme les ressources réseau détenues par l'exchange."""
        ...


def create_exchange(config: ScanConfig) -> ExchangeProtocol:
    """Instancie l'exchange CCXT configuré avec rate limiting et timeout.

    Raises:
        UnknownExchangeError: Si ``exchange_id`` ne désigne aucune classe CCXT.
    """
    exchange_class = getattr(ccxt, config.exchange_id, None)
    if exchange_class is None:
        raise UnknownExchangeError(f"Exchange CCXT inconnu: {config.exchange_id}")
    return exchange_class(
        {
            "enableRateLimit": True,
            "timeout": 30_000,
            "options": {"defaultType": config.market_type},
        }
    )


async def load_filtered_symbols(exchange: ExchangeProtocol, config: ScanConfig) -> list[str]:
    """Charge, filtre et trie les symboles compatibles avec un scan.

    Seuls les marchés actifs (ou sans drapeau explicite), du type et de la
    quote demandés sont conservés. ``max_pairs`` est appliqué après le tri.
    """
    markets = await exchange.load_markets()
    symbols: list[str] = []
    for symbol, market in markets.items():
        if market.get("active") is False:
            continue
        if market.get("type") != config.market_type:
            continue
        if market.get("quote") != config.quote:
            continue
        if config.exclude_stable_pairs and market.get("base") in STABLECOINS:
            continue
        symbols.append(symbol)

    symbols.sort()
    if config.max_pairs:
        symbols = symbols[: config.max_pairs]
    logger.info("%s symboles retenus", len(symbols))
    return symbols
