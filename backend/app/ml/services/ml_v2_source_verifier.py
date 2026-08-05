"""Vérification sans écriture d'un manifeste ML v2 contre SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.domain.backtesting import signal_profile_fingerprint
from app.domain.ohlcv_fingerprint import (
    BacktestInputFingerprint,
    InputDataStreamFingerprint,
)
from app.ml.models.ml_dataset_export import MLDatasetExportManifest
from app.ml.services.ml_v2_source import (
    build_ml_v2_source_config,
    ml_v2_source_identity,
)
from app.models.backtest import BacktestJob
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_engine import SQLiteHistoricalRepository
from app.services.backtest_input_data import load_backtest_input_snapshot

VerificationStatus = Literal["reproducible", "absent", "incompatible", "stale", "incomplete"]


@dataclass(frozen=True, slots=True)
class MLV2SourceVerificationResult:
    status: VerificationStatus
    reason: str
    expected_fingerprint: str | None
    calculated_fingerprint: str | None
    divergent_streams: tuple[dict[str, Any], ...] = ()

    @property
    def reproducible(self) -> bool:
        return self.status == "reproducible"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reproducible": self.reproducible,
            "reason": self.reason,
            "expected_input_data_fingerprint": self.expected_fingerprint,
            "calculated_input_data_fingerprint": self.calculated_fingerprint,
            "divergent_streams": list(self.divergent_streams),
        }


def _stream_differences(
    expected: tuple[InputDataStreamFingerprint, ...],
    calculated: tuple[InputDataStreamFingerprint, ...],
) -> tuple[dict[str, Any], ...]:
    expected_by_key = {item.sort_key(): item for item in expected}
    calculated_by_key = {item.sort_key(): item for item in calculated}
    differences: list[dict[str, Any]] = []
    for key in sorted(set(expected_by_key) | set(calculated_by_key)):
        left = expected_by_key.get(key)
        right = calculated_by_key.get(key)
        if left == right:
            continue
        if left is None or right is None:
            kind = "flux_absent"
        elif (
            left.candle_count != right.candle_count
            or left.effective_first_open_time_ms != right.effective_first_open_time_ms
            or left.effective_last_open_time_ms != right.effective_last_open_time_ms
        ):
            kind = "plage_ou_nombre"
        elif left.gaps_validated != right.gaps_validated:
            kind = "gap"
        elif left.fingerprint != right.fingerprint:
            kind = "contenu"
        else:
            kind = "metadonnees"
        item = left or right
        assert item is not None
        differences.append(
            {
                "type": kind,
                "role": item.role,
                "symbol": item.symbol,
                "timeframe": item.timeframe,
                "expected_fingerprint": left.fingerprint if left else None,
                "calculated_fingerprint": right.fingerprint if right else None,
                "expected_count": left.candle_count if left else None,
                "calculated_count": right.candle_count if right else None,
                "expected_bounds": (
                    [
                        left.effective_first_open_time_ms,
                        left.effective_last_open_time_ms,
                    ]
                    if left
                    else None
                ),
                "calculated_bounds": (
                    [
                        right.effective_first_open_time_ms,
                        right.effective_last_open_time_ms,
                    ]
                    if right
                    else None
                ),
            }
        )
    return tuple(differences)


class MLV2SourceVerifier:
    def __init__(self, backtests: BacktestRepository, candles: CandleRepository) -> None:
        self.backtests = backtests
        self.candles = candles

    async def verify(self, manifest: MLDatasetExportManifest) -> MLV2SourceVerificationResult:
        if manifest.manifest_schema_version != 2 or manifest.backtest_config is None:
            return MLV2SourceVerificationResult(
                "incompatible",
                "le manifeste ne possède pas le contrat reproductible ML v2",
                manifest.input_data_fingerprint,
                None,
            )
        config = manifest.backtest_config
        assert manifest.source_identity is not None
        assert manifest.input_data_fingerprint is not None
        try:
            canonical = build_ml_v2_source_config(
                symbol=config.symbols[0],
                timeframe=config.signal_config.timeframe,
                start=config.start,
                end=config.end,
                exchange_id=config.signal_config.exchange_id,
                market_type=config.signal_config.market_type,
                quote=config.signal_config.quote,
            )
        except ValueError as exc:
            return MLV2SourceVerificationResult(
                "incompatible", str(exc), manifest.input_data_fingerprint, None
            )
        if canonical != config or ml_v2_source_identity(config) != manifest.source_identity:
            return MLV2SourceVerificationResult(
                "incompatible",
                "la configuration canonique ou source_identity diverge",
                manifest.input_data_fingerprint,
                None,
            )
        if signal_profile_fingerprint(config.signal_config) != manifest.profile_fingerprint:
            return MLV2SourceVerificationResult(
                "incompatible",
                "le profile_fingerprint ne correspond pas au profil reconstruit",
                manifest.input_data_fingerprint,
                None,
            )
        try:
            snapshot = await load_backtest_input_snapshot(
                SQLiteHistoricalRepository(self.candles),
                BacktestJob(id="ml-v2-manifest-verification", config=config),
            )
            calculated = snapshot.fingerprint(manifest.source_identity)
        except ValueError as exc:
            return MLV2SourceVerificationResult(
                "incomplete", str(exc), manifest.input_data_fingerprint, None
            )
        expected = BacktestInputFingerprint(
            source_identity=manifest.source_identity,
            input_data_fingerprint=manifest.input_data_fingerprint,
            streams=tuple(manifest.input_streams),
        )
        differences = _stream_differences(expected.streams, calculated.streams)
        if expected != calculated:
            return MLV2SourceVerificationResult(
                "stale",
                "les données OHLCV ne correspondent pas au manifeste",
                expected.input_data_fingerprint,
                calculated.input_data_fingerprint,
                differences,
            )
        job = await self.backtests.get_job(manifest.source_job_id)
        if job is None:
            return MLV2SourceVerificationResult(
                "absent",
                "les données sont reproductibles mais le job source est absent",
                expected.input_data_fingerprint,
                calculated.input_data_fingerprint,
            )
        persisted = await self.backtests.get_ml_v2_source_input(job.id)
        if (
            job.config != config
            or persisted is None
            or persisted.confirmed_at_ms is None
            or persisted.fingerprint != expected
        ):
            return MLV2SourceVerificationResult(
                "incompatible",
                "le job source ou sa provenance persistée diverge du manifeste",
                expected.input_data_fingerprint,
                calculated.input_data_fingerprint,
            )
        return MLV2SourceVerificationResult(
            "reproducible",
            "configuration, job et tous les flux OHLCV correspondent",
            expected.input_data_fingerprint,
            calculated.input_data_fingerprint,
        )
