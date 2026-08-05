"""Résolution idempotente du backtest source canonique des datasets ML v2."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from app.core.settings import Timeframe
from app.domain.backtesting import signal_profile_fingerprint
from app.domain.candles import timeframe_milliseconds
from app.domain.limits import ma_ohlcv_limit, primary_ohlcv_limit
from app.ml.domain.ml_dataset_profile import (
    ML_DATASET_PROFILE_V2_ID,
    build_ml_dataset_profile_v2,
)
from app.ml.models.ml_dataset import ML_FEATURE_SCHEMA_VERSION_V2
from app.ml.services.ml_dataset_builder import MLDatasetBuilder, ML_DATASET_HORIZON
from app.models.backtest import (
    SIGNAL_EVALUATION_VERSION,
    BacktestConfig,
    BacktestJob,
    BacktestStatus,
)
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_manager import BacktestManager

ML_V2_SOURCE_IDENTITY_VERSION = "ml-v2-source-identity-v1"
SourceAction = Literal[
    "created",
    "reused",
    "resumed",
    "already-running",
    "would-create",
    "would-reuse",
    "would-resume",
]


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def build_ml_v2_source_config(
    *,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    exchange_id: str = "binance",
    market_type: Literal["spot", "swap", "future"] = "spot",
    quote: str | None = None,
) -> BacktestConfig:
    """Construit l'unique configuration de production admise pour un source v2."""
    normalized_symbol = symbol.strip().upper()
    if "/" not in normalized_symbol:
        raise ValueError("symbol doit utiliser la forme BASE/QUOTE, par exemple BTC/USDC")
    symbol_quote = normalized_symbol.rsplit("/", 1)[1]
    normalized_quote = (quote or symbol_quote).strip().upper()
    if symbol_quote != normalized_quote:
        raise ValueError("quote doit correspondre à la devise de cotation du symbole")

    profile = build_ml_dataset_profile_v2(
        timeframe=timeframe,
        quote=normalized_quote,
        exchange_id=exchange_id.strip().lower(),
        market_type=market_type,
    )
    return BacktestConfig(
        symbols=[normalized_symbol],
        start=start,
        end=end,
        signal_config=profile,
        signal_profile_id=ML_DATASET_PROFILE_V2_ID,
        horizons=[ML_DATASET_HORIZON],
        replay_mode="every_bar",
        entry_policy="signal_close",
        gap_policy="reject_range",
        fee_bps=0,
        slippage_bps=0,
        snapshot_status="confirmed",
        portfolio_simulation=None,
    )


def ml_v2_source_identity_payload(config: BacktestConfig) -> dict[str, Any]:
    """Retourne la représentation logique complète qui définit l'équivalence."""
    return {
        "identity_version": ML_V2_SOURCE_IDENTITY_VERSION,
        "algorithm_version": SIGNAL_EVALUATION_VERSION,
        "config": config.model_dump(mode="json"),
    }


def ml_v2_source_identity(config: BacktestConfig) -> str:
    serialized = _canonical_json(ml_v2_source_identity_payload(config))
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MLV2CoverageDiagnostic:
    name: str
    timeframe: str
    requested_start_ms: int
    requested_end_ms: int
    available_start_ms: int | None
    available_end_ms: int | None
    expected_count: int
    candle_count: int
    missing_ranges: tuple[tuple[int, int], ...]
    complete: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timeframe": self.timeframe,
            "requested_start_ms": self.requested_start_ms,
            "requested_end_ms": self.requested_end_ms,
            "available_start_ms": self.available_start_ms,
            "available_end_ms": self.available_end_ms,
            "expected_count": self.expected_count,
            "candle_count": self.candle_count,
            "missing_ranges": [list(item) for item in self.missing_ranges],
            "complete": self.complete,
        }


class MLV2SourceCoverageError(ValueError):
    """Diagnostic structuré d'un historique local insuffisant."""

    def __init__(self, diagnostics: tuple[MLV2CoverageDiagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        failures = [item for item in diagnostics if not item.complete]
        details = "; ".join(
            f"{item.name}/{item.timeframe}: {item.candle_count}/{item.expected_count}, "
            f"gaps={len(item.missing_ranges)}"
            for item in failures
        )
        super().__init__(
            "historique local insuffisant pour le source ML v2 ("
            + details
            + "). Préparez les bougies avec app.cli.backfill_candles."
        )


@dataclass(frozen=True, slots=True)
class MLV2SourceResult:
    action: SourceAction
    reason: str
    config: BacktestConfig
    source_identity: str
    profile_fingerprint: str
    job: BacktestJob | None
    coverage: tuple[MLV2CoverageDiagnostic, ...]
    dry_run: bool = False

    @property
    def can_export(self) -> bool:
        return self.job is not None and self.job.status == BacktestStatus.COMPLETED

    def as_dict(self) -> dict[str, Any]:
        job = self.job
        return {
            "action": self.action,
            "reason": self.reason,
            "dry_run": self.dry_run,
            "job_id": job.id if job else None,
            "status": job.status.value if job else None,
            "signal_profile_id": ML_DATASET_PROFILE_V2_ID,
            "feature_schema_version": ML_FEATURE_SCHEMA_VERSION_V2,
            "symbol": self.config.symbols[0],
            "timeframe": self.config.signal_config.timeframe,
            "window": {
                "start": self.config.start.isoformat(),
                "end": self.config.end.isoformat(),
            },
            "horizons": list(self.config.horizons),
            "fingerprints": {
                "source_identity": self.source_identity,
                "profile_fingerprint": self.profile_fingerprint,
                "dataset_version": job.dataset_version if job else None,
                "config_fingerprint": job.config_fingerprint if job else None,
            },
            "can_export": self.can_export,
            "coverage": [item.as_dict() for item in self.coverage],
            "canonical_config": self.config.model_dump(mode="json"),
        }


_SOURCE_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}


class MLV2SourceService:
    """Décide de réutiliser, reprendre ou créer un backtest source v2."""

    def __init__(
        self,
        backtests: BacktestRepository,
        candles: CandleRepository,
        manager: BacktestManager,
    ) -> None:
        self.backtests = backtests
        self.candles = candles
        self.manager = manager

    def _lock(self, identity: str) -> asyncio.Lock:
        key = (str(self.backtests.database.path.resolve()), identity)
        return _SOURCE_LOCKS.setdefault(key, asyncio.Lock())

    async def validate_coverage(self, config: BacktestConfig) -> tuple[MLV2CoverageDiagnostic, ...]:
        signal = config.signal_config
        symbol = config.symbols[0]
        start_ms = int(config.start.timestamp() * 1_000)
        end_ms = int(config.end.timestamp() * 1_000)
        interval = timeframe_milliseconds(signal.timeframe)
        warmup = primary_ohlcv_limit(signal)
        future = max(config.horizons) + int(config.entry_policy == "next_open") + 1
        windows = (
            ("primary-warmup", signal.timeframe, start_ms - warmup * interval, start_ms),
            ("decision-window", signal.timeframe, start_ms, end_ms),
            ("outcome-future", signal.timeframe, end_ms, end_ms + future * interval),
        )
        diagnostics: list[MLV2CoverageDiagnostic] = []
        for name, timeframe, window_start, window_end in windows:
            report = await self.candles.validate_backtest_coverage(
                exchange_id=signal.exchange_id,
                market_type=signal.market_type,
                symbol=symbol,
                timeframe=timeframe,
                start_time=window_start,
                end_time=window_end,
                closed_only=True,
            )
            diagnostics.append(
                MLV2CoverageDiagnostic(
                    name=name,
                    timeframe=timeframe,
                    requested_start_ms=window_start,
                    requested_end_ms=window_end,
                    available_start_ms=report.available_start,
                    available_end_ms=report.available_end,
                    expected_count=report.expected_count,
                    candle_count=report.candle_count,
                    missing_ranges=tuple(report.missing_ranges),
                    complete=report.is_complete,
                )
            )

        if signal.use_ma:
            higher_warmup = ma_ohlcv_limit(signal)
            primary_end_with_future = end_ms + future * interval
            for higher_timeframe in signal.ma_timeframes:
                if higher_timeframe == signal.timeframe:
                    continue
                higher_interval = timeframe_milliseconds(higher_timeframe)
                before = await self.candles.get_candles_before(
                    exchange_id=signal.exchange_id,
                    market_type=signal.market_type,
                    symbol=symbol,
                    timeframe=higher_timeframe,
                    before_open_time=start_ms,
                    limit=higher_warmup,
                    closed_only=True,
                )
                gaps = tuple(
                    (left.open_time + higher_interval, right.open_time)
                    for left, right in zip(before, before[1:])
                    if right.open_time - left.open_time != higher_interval
                )
                diagnostics.append(
                    MLV2CoverageDiagnostic(
                        name="trend-warmup",
                        timeframe=higher_timeframe,
                        requested_start_ms=start_ms - higher_warmup * higher_interval,
                        requested_end_ms=start_ms,
                        available_start_ms=before[0].open_time if before else None,
                        available_end_ms=before[-1].open_time if before else None,
                        expected_count=higher_warmup,
                        candle_count=len(before),
                        missing_ranges=gaps,
                        complete=len(before) == higher_warmup and not gaps,
                    )
                )
                current = await self.candles.get_range(
                    signal.exchange_id,
                    signal.market_type,
                    symbol,
                    higher_timeframe,
                    from_time=start_ms,
                    to_time=primary_end_with_future,
                    limit=2_000_000,
                    closed_only=True,
                )
                current_gaps = tuple(
                    (left.open_time + higher_interval, right.open_time)
                    for left, right in zip(current, current[1:])
                    if right.open_time - left.open_time != higher_interval
                )
                diagnostics.append(
                    MLV2CoverageDiagnostic(
                        name="trend-window",
                        timeframe=higher_timeframe,
                        requested_start_ms=start_ms,
                        requested_end_ms=primary_end_with_future,
                        available_start_ms=current[0].open_time if current else None,
                        available_end_ms=current[-1].open_time if current else None,
                        expected_count=len(current),
                        candle_count=len(current),
                        missing_ranges=current_gaps,
                        complete=not current_gaps,
                    )
                )

        result = tuple(diagnostics)
        if any(not item.complete for item in result):
            raise MLV2SourceCoverageError(result)
        return result

    async def _matching_historical_job(
        self, config: BacktestConfig, identity: str
    ) -> BacktestJob | None:
        offset = 0
        while True:
            jobs, total = await self.backtests.list_jobs(offset=offset, limit=200)
            for job in jobs:
                if (
                    job.algorithm_version == SIGNAL_EVALUATION_VERSION
                    and ml_v2_source_identity(job.config) == identity
                ):
                    return job
            offset += len(jobs)
            if offset >= total or not jobs:
                return None

    async def _claimed_job(self, identity: str) -> BacktestJob | None:
        try:
            return await self.backtests.get_ml_v2_source_claim(identity)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            return None

    async def _completed_is_usable(self, job: BacktestJob) -> bool:
        try:
            await MLDatasetBuilder(self.backtests).build(
                job.id,
                feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
            )
        except ValueError:
            return False
        return True

    async def _select(self, config: BacktestConfig, identity: str) -> BacktestJob | None:
        return await self._claimed_job(identity) or await self._matching_historical_job(
            config, identity
        )

    async def prepare(
        self,
        config: BacktestConfig,
        *,
        dry_run: bool = False,
        wait_for_running: bool = False,
    ) -> MLV2SourceResult:
        identity = ml_v2_source_identity(config)
        profile_fingerprint = signal_profile_fingerprint(config.signal_config)
        async with self._lock(identity):
            selected = await self._select(config, identity)

            if selected is not None and (
                selected.algorithm_version != SIGNAL_EVALUATION_VERSION
                or ml_v2_source_identity(selected.config) != identity
            ):
                replace_job_id = selected.id
                reason = "revendication incompatible avec le contrat courant; nouveau job créé"
            elif selected is not None and selected.status == BacktestStatus.COMPLETED:
                if await self._completed_is_usable(selected):
                    if not dry_run:
                        claimed_id, _ = await self.backtests.adopt_ml_v2_source(
                            identity,
                            selected.id,
                            algorithm_version=SIGNAL_EVALUATION_VERSION,
                        )
                        selected = await self.backtests.get_job(claimed_id) or selected
                    return MLV2SourceResult(
                        action=cast(SourceAction, "would-reuse" if dry_run else "reused"),
                        reason="source terminé, canonique et exportable",
                        config=config,
                        source_identity=identity,
                        profile_fingerprint=profile_fingerprint,
                        job=selected,
                        coverage=(),
                        dry_run=dry_run,
                    )
                replace_job_id = selected.id
                reason = "source terminé mais inexploitable; création d'un remplacement"
            elif selected is not None and selected.status in {
                BacktestStatus.PENDING,
                BacktestStatus.RUNNING,
            }:
                if wait_for_running and not dry_run:
                    selected = await self.manager.wait_until_terminal(selected.id)
                return MLV2SourceResult(
                    action="already-running",
                    reason="un source compatible est déjà en cours",
                    config=config,
                    source_identity=identity,
                    profile_fingerprint=profile_fingerprint,
                    job=selected,
                    coverage=(),
                    dry_run=dry_run,
                )
            elif selected is not None and selected.status == BacktestStatus.INTERRUPTED:
                checkpoint = selected.checkpoint
                resumable = bool(
                    checkpoint and checkpoint.get("algorithm_version") == SIGNAL_EVALUATION_VERSION
                )
                if resumable:
                    coverage = await self.validate_coverage(config)
                    if dry_run:
                        return MLV2SourceResult(
                            action="would-resume",
                            reason="source interrompu avec checkpoint compatible",
                            config=config,
                            source_identity=identity,
                            profile_fingerprint=profile_fingerprint,
                            job=selected,
                            coverage=coverage,
                            dry_run=True,
                        )
                    resumed = await self.manager.resume(selected.id)
                    if resumed is None:
                        raise RuntimeError("le source à reprendre a disparu")
                    terminal = await self.manager.wait_until_terminal(resumed.id)
                    return MLV2SourceResult(
                        action="resumed",
                        reason="source interrompu repris depuis son checkpoint durable",
                        config=config,
                        source_identity=identity,
                        profile_fingerprint=profile_fingerprint,
                        job=terminal,
                        coverage=coverage,
                    )
                replace_job_id = selected.id
                reason = "source interrompu sans checkpoint compatible; nouveau job créé"
            elif selected is not None:
                replace_job_id = selected.id
                reason = f"source {selected.status.value} non réutilisable; nouveau job créé"
            else:
                replace_job_id = None
                reason = "aucun source compatible existant"

            coverage = await self.validate_coverage(config)
            if dry_run:
                return MLV2SourceResult(
                    action="would-create",
                    reason=reason,
                    config=config,
                    source_identity=identity,
                    profile_fingerprint=profile_fingerprint,
                    job=selected,
                    coverage=coverage,
                    dry_run=True,
                )

            job, created = await self.manager.create_ml_v2_source_job(
                config,
                identity,
                replace_job_id=replace_job_id,
            )
            if not created:
                concurrent_action: SourceAction = (
                    "reused" if job.status == BacktestStatus.COMPLETED else "already-running"
                )
                return MLV2SourceResult(
                    action=concurrent_action,
                    reason="une invocation concurrente a réservé ce source logique",
                    config=config,
                    source_identity=identity,
                    profile_fingerprint=profile_fingerprint,
                    job=job,
                    coverage=coverage,
                )
            terminal = await self.manager.wait_until_terminal(job.id)
            return MLV2SourceResult(
                action="created",
                reason=reason,
                config=config,
                source_identity=identity,
                profile_fingerprint=profile_fingerprint,
                job=terminal,
                coverage=coverage,
            )
