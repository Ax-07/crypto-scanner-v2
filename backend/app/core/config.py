"""Charge la configuration globale du processus depuis l'environnement.

Cette configuration couvre le CORS et la rétention des jobs. La configuration
métier propre à chaque scan est définie séparément par ``ScanConfig``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    """Lit un booléen d'environnement avec des valeurs textuelles explicites."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _database_path() -> Path:
    """Résout un chemin de base stable, indépendamment du dossier de lancement."""
    configured = Path(os.getenv("DATABASE_PATH", "data/scanner_crypto.sqlite3")).expanduser()
    return (
        configured.resolve() if configured.is_absolute() else (BACKEND_ROOT / configured).resolve()
    )


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Paramètres immuables partagés par l'application FastAPI.

    Attributes:
        cors_origins: Origines autorisées par le middleware CORS.
        completed_job_ttl_seconds: Durée de conservation des jobs terminés.
        max_retained_jobs: Nombre maximal de jobs conservés en mémoire.
    """

    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    completed_job_ttl_seconds: int = 3_600
    max_retained_jobs: int = 100
    database_path: Path = BACKEND_ROOT / "data" / "scanner_crypto.sqlite3"
    candle_storage_enabled: bool = True
    candle_sync_enabled: bool = True
    candle_default_limit: int = 500
    candle_max_api_limit: int = 5_000
    candle_indicator_warmup_bars: int = 500
    market_history_window_before: int = 500
    market_history_window_after: int = 500
    candle_gap_repair_enabled: bool = True
    candle_sync_page_limit: int = 1_000
    candle_sync_max_pages: int = 100
    candle_open_write_interval_seconds: float = 5.0
    backfill_default_exchange: str = "binance"
    backfill_default_market_type: str = "spot"
    backfill_default_quote: str = "USDC"
    backfill_default_timeframes: tuple[str, ...] = ()
    backfill_page_limit: int = 1_000
    backfill_max_concurrency: int = 2
    backfill_max_retries: int = 5
    backfill_retry_delay_seconds: float = 2.0
    backfill_progress_interval_seconds: float = 5.0
    backfill_overlap_candles: int = 2
    backfill_repair_gaps: bool = True
    shadow_mode_enabled: bool = False


def get_app_settings() -> AppSettings:
    """Construit les paramètres applicatifs à partir des variables d'environnement.

    Les valeurs numériques sont bornées à 60 secondes pour le TTL et à un job
    pour la rétention. Une origine CORS vide est ignorée.

    Returns:
        Paramètres applicatifs prêts à être injectés dans l'application.

    Raises:
        ValueError: Si une variable numérique ne contient pas un entier.
    """
    origins = tuple(
        item.strip()
        for item in os.getenv("CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",")
        if item.strip()
    )
    from app.core.settings import PROJECT_TIMEFRAMES

    configured_timeframes = tuple(
        item.strip()
        for item in os.getenv("BACKFILL_DEFAULT_TIMEFRAMES", ",".join(PROJECT_TIMEFRAMES)).split(
            ","
        )
        if item.strip()
    )
    unknown_timeframes = set(configured_timeframes) - set(PROJECT_TIMEFRAMES)
    if unknown_timeframes:
        raise ValueError(f"BACKFILL_DEFAULT_TIMEFRAMES invalides: {sorted(unknown_timeframes)}")
    return AppSettings(
        cors_origins=origins,
        completed_job_ttl_seconds=max(60, int(os.getenv("JOB_TTL_SECONDS", "3600"))),
        max_retained_jobs=max(1, int(os.getenv("MAX_RETAINED_JOBS", "100"))),
        database_path=_database_path(),
        candle_storage_enabled=_env_bool("CANDLE_STORAGE_ENABLED", True),
        candle_sync_enabled=_env_bool("CANDLE_SYNC_ENABLED", True),
        candle_default_limit=max(1, int(os.getenv("CANDLE_DEFAULT_LIMIT", "500"))),
        candle_max_api_limit=max(1, int(os.getenv("CANDLE_MAX_API_LIMIT", "5000"))),
        candle_indicator_warmup_bars=max(
            100, int(os.getenv("CANDLE_INDICATOR_WARMUP_BARS", "500"))
        ),
        market_history_window_before=max(1, int(os.getenv("MARKET_HISTORY_WINDOW_BEFORE", "500"))),
        market_history_window_after=max(1, int(os.getenv("MARKET_HISTORY_WINDOW_AFTER", "500"))),
        candle_gap_repair_enabled=_env_bool("CANDLE_GAP_REPAIR_ENABLED", True),
        candle_sync_page_limit=max(1, int(os.getenv("CANDLE_SYNC_PAGE_LIMIT", "1000"))),
        candle_sync_max_pages=max(1, int(os.getenv("CANDLE_SYNC_MAX_PAGES", "100"))),
        candle_open_write_interval_seconds=max(
            0.0, float(os.getenv("CANDLE_OPEN_WRITE_INTERVAL_SECONDS", "5"))
        ),
        backfill_default_exchange=os.getenv("BACKFILL_DEFAULT_EXCHANGE", "binance").strip().lower(),
        backfill_default_market_type=os.getenv("BACKFILL_DEFAULT_MARKET_TYPE", "spot")
        .strip()
        .lower(),
        backfill_default_quote=os.getenv("BACKFILL_DEFAULT_QUOTE", "USDC").strip().upper(),
        backfill_default_timeframes=configured_timeframes,
        backfill_page_limit=max(1, int(os.getenv("BACKFILL_PAGE_LIMIT", "1000"))),
        backfill_max_concurrency=max(1, int(os.getenv("BACKFILL_MAX_CONCURRENCY", "2"))),
        backfill_max_retries=max(0, int(os.getenv("BACKFILL_MAX_RETRIES", "5"))),
        backfill_retry_delay_seconds=max(
            0.1, float(os.getenv("BACKFILL_RETRY_DELAY_SECONDS", "2"))
        ),
        backfill_progress_interval_seconds=max(
            0.1, float(os.getenv("BACKFILL_PROGRESS_INTERVAL_SECONDS", "5"))
        ),
        backfill_overlap_candles=max(1, int(os.getenv("BACKFILL_OVERLAP_CANDLES", "2"))),
        backfill_repair_gaps=_env_bool("BACKFILL_REPAIR_GAPS", True),
        shadow_mode_enabled=_env_bool("SHADOW_MODE_ENABLED", False),
    )
