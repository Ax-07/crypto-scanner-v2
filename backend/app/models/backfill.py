"""Modèles typés du catalogue et du backfill historique."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class BackfillStatus(StrEnum):
    """États persistants d'une cible ou d'une exécution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class MarketRecord:
    """Métadonnées stables et non sensibles d'un marché CCXT."""

    exchange_id: str
    market_type: str
    symbol: str
    base: str
    quote: str
    exchange_market_id: str | None
    active: bool
    spot: bool
    margin: bool | None = None
    contract: bool | None = None
    amount_precision: float | None = None
    price_precision: float | None = None
    min_amount: float | None = None
    min_cost: float | None = None
    raw_metadata_json: str | None = None


@dataclass(slots=True)
class SyncState:
    """Checkpoint persistant d'un couple symbole/timeframe."""

    exchange_id: str
    market_type: str
    symbol: str
    timeframe: str
    status: BackfillStatus = BackfillStatus.PENDING
    requested_from: int | None = None
    requested_to: int | None = None
    earliest_available_time: int | None = None
    latest_available_time: int | None = None
    next_since: int | None = None
    pages_downloaded: int = 0
    candles_downloaded: int = 0
    candles_upserted: int = 0
    retry_count: int = 0
    gap_count: int = 0
    last_error: str | None = None
    started_at: int | None = None
    completed_at: int | None = None
    updated_at: int = 0


@dataclass(frozen=True, slots=True)
class BackfillOptions:
    """Options validées transmises au service, indépendantes d'argparse."""

    exchange_id: str = "binance"
    market_type: str = "spot"
    quote: str = "USDC"
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    from_time: int | None = None
    to_time: int | None = None
    resume: bool = True
    restart: bool = False
    include_inactive: bool = False
    max_concurrency: int = 2
    page_limit: int = 1_000
    max_retries: int = 5
    retry_delay_seconds: float = 2.0
    progress_interval_seconds: float = 5.0
    overlap_candles: int = 2
    repair_gaps: bool = False
    execute: bool = False
    mode: str = "backfill"

    def as_json_dict(self) -> dict[str, object]:
        """Retourne une représentation JSON sérialisable."""
        return asdict(self)


@dataclass(slots=True)
class TargetResult:
    """Résultat synthétique d'une cible de backfill."""

    symbol: str
    timeframe: str
    status: BackfillStatus
    pages: int = 0
    candles: int = 0
    earliest: int | None = None
    latest: int | None = None
    gaps: int = 0
    repaired_gaps: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Couverture déterministe d'une plage destinée au backtesting."""

    requested_start: int
    requested_end: int
    available_start: int | None
    available_end: int | None
    candle_count: int
    expected_count: int
    missing_ranges: list[tuple[int, int]]
    is_complete: bool


@dataclass(slots=True)
class BackfillReport:
    """Rapport global sérialisable d'une simulation ou exécution."""

    run_id: str
    exchange_id: str
    market_type: str
    quote: str
    execute: bool
    discovered_symbols: int
    selected_symbols: list[str]
    selected_timeframes: list[str]
    skipped_timeframes: list[str]
    total_targets: int
    database_size_bytes: int
    free_space_bytes: int | None
    started_at: int
    database_file: str = "scanner_crypto.sqlite3"
    completed_at: int | None = None
    results: list[TargetResult] = field(default_factory=list)
    resume_command: str = ""

    def as_dict(self) -> dict[str, object]:
        """Produit un dictionnaire JSON complet avec agrégats."""
        results = [asdict(result) for result in self.results]
        earliest_values = [
            result.earliest for result in self.results if result.earliest is not None
        ]
        latest_values = [result.latest for result in self.results if result.latest is not None]
        completed_at = self.completed_at or self.started_at
        return {
            **asdict(self),
            "results": results,
            "completed_targets": sum(
                result.status is BackfillStatus.COMPLETED for result in self.results
            ),
            "partial_targets": sum(
                result.status is BackfillStatus.PARTIAL for result in self.results
            ),
            "failed_targets": sum(
                result.status is BackfillStatus.FAILED for result in self.results
            ),
            "total_pages": sum(result.pages for result in self.results),
            "total_candles": sum(result.candles for result in self.results),
            "gap_count": sum(result.gaps for result in self.results),
            "repaired_gap_count": sum(result.repaired_gaps for result in self.results),
            "global_earliest": min(earliest_values) if earliest_values else None,
            "global_latest": max(latest_values) if latest_values else None,
            "duration_seconds": round((completed_at - self.started_at) / 1_000, 3),
            "errors": [
                {
                    "symbol": result.symbol,
                    "timeframe": result.timeframe,
                    "error": result.error,
                }
                for result in self.results
                if result.error
            ],
        }
