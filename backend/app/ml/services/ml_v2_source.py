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
from app.domain.ohlcv_fingerprint import BacktestInputFingerprint
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
from app.services.backtest_engine import SQLiteHistoricalRepository
from app.services.backtest_input_data import (
    BacktestInputSnapshot,
    load_backtest_input_snapshot,
)

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
    input_fingerprint: BacktestInputFingerprint | None = None
    stale_job_id: str | None = None
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
                "input_data_fingerprint": (
                    self.input_fingerprint.input_data_fingerprint
                    if self.input_fingerprint is not None
                    else None
                ),
                "input_data_fingerprint_version": (
                    self.input_fingerprint.fingerprint_version
                    if self.input_fingerprint is not None
                    else None
                ),
                "dataset_version": job.dataset_version if job else None,
                "config_fingerprint": job.config_fingerprint if job else None,
            },
            "can_export": self.can_export,
            "stale_job_id": self.stale_job_id,
            "input_streams": (
                [stream.model_dump(mode="json") for stream in self.input_fingerprint.streams]
                if self.input_fingerprint is not None
                else []
            ),
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

    def _coverage_from_snapshot(
        self, config: BacktestConfig, snapshot: BacktestInputSnapshot
    ) -> tuple[MLV2CoverageDiagnostic, ...]:
        signal = config.signal_config
        start_ms = int(config.start.timestamp() * 1_000)
        end_ms = int(config.end.timestamp() * 1_000)
        interval = timeframe_milliseconds(signal.timeframe)
        diagnostics: list[MLV2CoverageDiagnostic] = []
        for symbol, series in snapshot.primary.items():
            del symbol
            partitions = (
                (
                    "primary-warmup",
                    series.candles[: series.first_decision_index],
                    primary_ohlcv_limit(signal),
                ),
                (
                    "decision-window",
                    series.candles[series.first_decision_index : series.last_decision_index + 1],
                    (end_ms - start_ms) // interval,
                ),
                (
                    "outcome-future",
                    series.candles[series.last_decision_index + 1 :],
                    max(config.horizons) + int(config.entry_policy == "next_open") + 1,
                ),
            )
            for name, candles, expected in partitions:
                gaps = tuple(
                    (left.open_time + interval, right.open_time)
                    for left, right in zip(candles, candles[1:])
                    if right.open_time - left.open_time != interval
                )
                diagnostics.append(
                    MLV2CoverageDiagnostic(
                        name=name,
                        timeframe=signal.timeframe,
                        requested_start_ms=(candles[0].open_time if candles else start_ms),
                        requested_end_ms=(candles[-1].open_time + interval if candles else end_ms),
                        available_start_ms=candles[0].open_time if candles else None,
                        available_end_ms=candles[-1].open_time if candles else None,
                        expected_count=expected,
                        candle_count=len(candles),
                        missing_ranges=gaps,
                        complete=len(candles) == expected and not gaps,
                    )
                )
        higher_warmup = ma_ohlcv_limit(signal)
        for symbol_trends in snapshot.trends.values():
            for timeframe, candles in symbol_trends.items():
                higher_interval = timeframe_milliseconds(timeframe)
                before = [item for item in candles if item.open_time < start_ms]
                current = [item for item in candles if item.open_time >= start_ms]
                for name, items, expected in (
                    ("trend-warmup", before, higher_warmup),
                    ("trend-window", current, len(current)),
                ):
                    gaps = tuple(
                        (left.open_time + higher_interval, right.open_time)
                        for left, right in zip(items, items[1:])
                        if right.open_time - left.open_time != higher_interval
                    )
                    diagnostics.append(
                        MLV2CoverageDiagnostic(
                            name=name,
                            timeframe=timeframe,
                            requested_start_ms=(items[0].open_time if items else start_ms),
                            requested_end_ms=(
                                items[-1].open_time + higher_interval if items else end_ms
                            ),
                            available_start_ms=items[0].open_time if items else None,
                            available_end_ms=items[-1].open_time if items else None,
                            expected_count=expected,
                            candle_count=len(items),
                            missing_ranges=gaps,
                            complete=len(items) == expected and not gaps,
                        )
                    )
        result = tuple(diagnostics)
        if any(not item.complete for item in result):
            raise MLV2SourceCoverageError(result)
        return result

    async def _current_inputs(
        self, config: BacktestConfig, identity: str
    ) -> tuple[BacktestInputFingerprint, tuple[MLV2CoverageDiagnostic, ...]]:
        preview_job = BacktestJob(id="ml-v2-input-preview", config=config)
        try:
            snapshot = await load_backtest_input_snapshot(
                SQLiteHistoricalRepository(self.candles), preview_job
            )
        except ValueError as exc:
            start_ms = int(config.start.timestamp() * 1_000)
            interval = timeframe_milliseconds(config.signal_config.timeframe)
            expected = primary_ohlcv_limit(config.signal_config)
            diagnostic = MLV2CoverageDiagnostic(
                name="primary-warmup",
                timeframe=config.signal_config.timeframe,
                requested_start_ms=start_ms - expected * interval,
                requested_end_ms=start_ms,
                available_start_ms=None,
                available_end_ms=None,
                expected_count=expected,
                candle_count=0,
                missing_ranges=(),
                complete=False,
            )
            raise MLV2SourceCoverageError((diagnostic,)) from exc
        coverage = self._coverage_from_snapshot(config, snapshot)
        return snapshot.fingerprint(identity), coverage

    async def validate_coverage(self, config: BacktestConfig) -> tuple[MLV2CoverageDiagnostic, ...]:
        _, coverage = await self._current_inputs(config, ml_v2_source_identity(config))
        return coverage

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
            current_input, coverage = await self._current_inputs(config, identity)
            selected = await self._select(config, identity)
            selected_input = (
                await self.backtests.get_ml_v2_source_input(selected.id)
                if selected is not None
                else None
            )
            input_matches = bool(
                selected_input is not None and selected_input.fingerprint == current_input
            )
            stale_job_id: str | None = None

            if selected is not None and (
                selected.algorithm_version != SIGNAL_EVALUATION_VERSION
                or ml_v2_source_identity(selected.config) != identity
            ):
                replace_job_id = selected.id
                reason = "revendication incompatible avec le contrat courant; nouveau job créé"
            elif selected is not None and selected.status == BacktestStatus.COMPLETED:
                if (
                    input_matches
                    and selected_input is not None
                    and selected_input.confirmed_at_ms is not None
                    and await self._completed_is_usable(selected)
                ):
                    return MLV2SourceResult(
                        action=cast(SourceAction, "would-reuse" if dry_run else "reused"),
                        reason="source terminé, canonique, exportable et OHLCV identique",
                        config=config,
                        source_identity=identity,
                        profile_fingerprint=profile_fingerprint,
                        job=selected,
                        coverage=coverage,
                        input_fingerprint=current_input,
                        dry_run=dry_run,
                    )
                replace_job_id = selected.id
                stale_job_id = selected.id
                reason = (
                    "source terminé sans fingerprint fort confirmé; nouveau calcul requis"
                    if selected_input is None or selected_input.confirmed_at_ms is None
                    else "source stale: contenu OHLCV divergent; nouveau job créé"
                )
            elif selected is not None and selected.status in {
                BacktestStatus.PENDING,
                BacktestStatus.RUNNING,
            }:
                if input_matches:
                    if wait_for_running and not dry_run:
                        selected = await self.manager.wait_until_terminal(selected.id)
                    return MLV2SourceResult(
                        action="already-running",
                        reason="un source compatible fingerprinté est déjà en cours",
                        config=config,
                        source_identity=identity,
                        profile_fingerprint=profile_fingerprint,
                        job=selected,
                        coverage=coverage,
                        input_fingerprint=current_input,
                        dry_run=dry_run,
                    )
                replace_job_id = selected.id
                stale_job_id = selected.id
                reason = "source en cours basé sur d'autres données; nouvelle génération requise"
            elif selected is not None and selected.status == BacktestStatus.INTERRUPTED:
                checkpoint = selected.checkpoint
                resumable = bool(
                    checkpoint
                    and checkpoint.get("algorithm_version") == SIGNAL_EVALUATION_VERSION
                    and input_matches
                )
                if resumable:
                    if dry_run:
                        return MLV2SourceResult(
                            action="would-resume",
                            reason="source interrompu avec checkpoint compatible",
                            config=config,
                            source_identity=identity,
                            profile_fingerprint=profile_fingerprint,
                            job=selected,
                            coverage=coverage,
                            input_fingerprint=current_input,
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
                        input_fingerprint=current_input,
                    )
                replace_job_id = selected.id
                stale_job_id = selected.id
                reason = "source interrompu sans checkpoint/fingerprint compatible; nouveau job"
            elif selected is not None:
                replace_job_id = selected.id
                reason = f"source {selected.status.value} non réutilisable; nouveau job créé"
            else:
                replace_job_id = None
                reason = "aucun source compatible existant"

            if dry_run:
                return MLV2SourceResult(
                    action="would-create",
                    reason=reason,
                    config=config,
                    source_identity=identity,
                    profile_fingerprint=profile_fingerprint,
                    job=selected,
                    coverage=coverage,
                    input_fingerprint=current_input,
                    stale_job_id=stale_job_id,
                    dry_run=True,
                )

            job, created = await self.manager.create_ml_v2_source_job(
                config,
                identity,
                input_fingerprint=current_input,
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
                    input_fingerprint=current_input,
                    stale_job_id=stale_job_id,
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
                input_fingerprint=current_input,
                stale_job_id=stale_job_id,
            )
