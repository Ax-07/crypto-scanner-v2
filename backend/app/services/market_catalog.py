"""Découverte et persistance du catalogue de marchés CCXT."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.models.backfill import MarketRecord
from app.repositories.market_repository import MarketRepository


def _number(value: object) -> float | None:
    """Convertit une métadonnée numérique optionnelle."""
    return float(value) if isinstance(value, (int, float)) else None


class MarketCatalogService:
    """Sélectionne tous les marchés d'une quote sans filtres du scanner."""

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def discover(
        self,
        exchange: Any,
        *,
        exchange_id: str,
        market_type: str,
        quote: str,
        include_inactive: bool,
        persist: bool,
    ) -> list[MarketRecord]:
        """Charge, filtre et trie le catalogue courant de l'exchange."""
        raw_markets = await exchange.load_markets()
        selected: list[MarketRecord] = []
        seen: set[str] = set()
        for symbol, raw in raw_markets.items():
            if not isinstance(raw, Mapping):
                continue
            active = raw.get("active") is not False
            if raw.get("type") != market_type or raw.get("quote") != quote:
                continue
            if market_type == "spot" and raw.get("spot") is False:
                continue
            if not include_inactive and not active:
                continue
            canonical = str(symbol)
            if "/" not in canonical:
                continue
            seen.add(canonical)
            precision = raw.get("precision")
            limits = raw.get("limits")
            amount_limit = limits.get("amount", {}) if isinstance(limits, Mapping) else {}
            cost_limit = limits.get("cost", {}) if isinstance(limits, Mapping) else {}
            useful = {
                "type": raw.get("type"),
                "settle": raw.get("settle"),
                "linear": raw.get("linear"),
                "inverse": raw.get("inverse"),
            }
            selected.append(
                MarketRecord(
                    exchange_id=exchange_id,
                    market_type=market_type,
                    symbol=canonical,
                    base=str(raw.get("base") or canonical.split("/", 1)[0]),
                    quote=str(raw.get("quote") or quote),
                    exchange_market_id=(str(raw["id"]) if raw.get("id") is not None else None),
                    active=active,
                    spot=bool(raw.get("spot", market_type == "spot")),
                    margin=(bool(raw["margin"]) if raw.get("margin") is not None else None),
                    contract=(bool(raw["contract"]) if raw.get("contract") is not None else None),
                    amount_precision=(
                        _number(precision.get("amount")) if isinstance(precision, Mapping) else None
                    ),
                    price_precision=(
                        _number(precision.get("price")) if isinstance(precision, Mapping) else None
                    ),
                    min_amount=_number(amount_limit.get("min")),
                    min_cost=_number(cost_limit.get("min")),
                    raw_metadata_json=json.dumps(useful, sort_keys=True),
                )
            )
        selected.sort(key=lambda market: market.symbol)
        if persist:
            await self.repository.upsert_many(selected)
            await self.repository.mark_missing_inactive(exchange_id, market_type, seen)
        return selected
