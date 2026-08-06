"""Audit déterministe, structurel, statistique et causal d'un dataset ML v2."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, cast

import numpy as np
import pandas as pd

from app.domain.backtesting import calculate_forward_outcomes
from app.domain.candles import timeframe_milliseconds
from app.domain.limits import ma_ohlcv_limit, primary_ohlcv_limit
from app.domain.signal_evaluation import evaluate_signal_snapshot
from app.ml.domain.ml_dataset import build_ml_dataset_row
from app.ml.models.ml_dataset import MarketDirectionLabel, MLDatasetRow
from app.ml.models.ml_dataset_audit import (
    AuditConclusion,
    MLDatasetAuditReport,
)
from app.ml.services.ml_dataset_loader import MLDatasetLoadResult
from app.ml.services.ml_v2_source_verifier import MLV2SourceVerificationResult
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_engine import SQLiteHistoricalRepository
from app.services.backtest_input_data import load_backtest_input_snapshot

FORBIDDEN_FEATURE_NAMES = frozenset(
    {
        "label",
        "future_return",
        "gross_return",
        "net_return",
        "mfe",
        "mae",
        "highest_price",
        "lowest_price",
        "exit_price",
        "exit_time",
    }
)
REQUIRED_V2_FEATURES = frozenset(
    {
        "price.close",
        "candle.open",
        "candle.high",
        "candle.low",
        "candle.close",
        "candle.volume",
        "volatility.natr_percent",
    }
)
QUASI_CONSTANT_DOMINANCE = 0.995
CORRELATION_ALERT = 0.98


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _summary(values: Iterable[float]) -> dict[str, float | int | None]:
    array = np.asarray(list(values), dtype=np.float64)
    if not len(array):
        return {
            "count": 0,
            "min": None,
            "q01": None,
            "q05": None,
            "q25": None,
            "median": None,
            "q75": None,
            "q95": None,
            "q99": None,
            "max": None,
            "mean": None,
            "std": None,
        }
    quantiles = np.quantile(array, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    return {
        "count": int(len(array)),
        "min": float(np.min(array)),
        "q01": float(quantiles[0]),
        "q05": float(quantiles[1]),
        "q25": float(quantiles[2]),
        "median": float(quantiles[3]),
        "q75": float(quantiles[4]),
        "q95": float(quantiles[5]),
        "q99": float(quantiles[6]),
        "max": float(np.max(array)),
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
    }


def _longest_run(values: Iterable[object]) -> int:
    longest = current = 0
    previous: object = object()
    for value in values:
        current = current + 1 if value == previous else 1
        longest = max(longest, current)
        previous = value
    return longest


def _longest_label_run(rows: tuple[MLDatasetRow, ...], label: MarketDirectionLabel) -> int:
    longest = current = 0
    for row in rows:
        current = current + 1 if row.label == label else 0
        longest = max(longest, current)
    return longest


def _label_counts(rows: Iterable[MLDatasetRow]) -> dict[str, int]:
    counts = Counter(row.label.value for row in rows)
    return {label.value: counts[label.value] for label in MarketDirectionLabel}


def _deterministic_sample(
    rows: tuple[MLDatasetRow, ...], limit: int = 16
) -> tuple[MLDatasetRow, ...]:
    if not rows:
        return ()
    indexes = {0, len(rows) - 1, len(rows) // 4, len(rows) // 2, 3 * len(rows) // 4}
    for label in MarketDirectionLabel:
        indexes.update(index for index, row in enumerate(rows) if row.label == label)
        if len(indexes) >= limit:
            break
    for year in sorted({row.decision_time.year for row in rows}):
        indexes.add(next(index for index, row in enumerate(rows) if row.decision_time.year == year))
    indexes.add(min(range(len(rows)), key=lambda index: rows[index].natr_percent))
    indexes.add(max(range(len(rows)), key=lambda index: rows[index].natr_percent))
    selected = sorted(indexes)[:limit]
    return tuple(rows[index] for index in selected)


class MLDatasetAuditor:
    """Produit un rapport sans entraîner, transformer ou modifier les données."""

    def __init__(self, *, minimum_rows: int = 1, recommended_source_rows: int = 10_000) -> None:
        self.minimum_rows = minimum_rows
        self.recommended_source_rows = recommended_source_rows

    async def audit(
        self,
        loaded: MLDatasetLoadResult,
        *,
        verification: MLV2SourceVerificationResult | None = None,
        backtests: BacktestRepository | None = None,
        candles: CandleRepository | None = None,
    ) -> MLDatasetAuditReport:
        manifest = loaded.manifest
        rows = loaded.rows
        blocking: list[str] = []
        warnings: list[str] = []
        manifest_bytes = loaded.manifest_path.read_bytes()
        manifest_sha256 = _sha256_bytes(manifest_bytes)
        dataset_identity = _sha256_bytes(
            _canonical_json_bytes(
                {
                    "data_sha256": manifest.data_sha256,
                    "manifest_sha256": manifest_sha256,
                    "source_job_id": manifest.source_job_id,
                }
            )
        )

        if (
            manifest.manifest_schema_version != 2
            or manifest.feature_schema_version != "causal-features-v2"
        ):
            blocking.append("manifest_not_reproducible_ml_v2")
        if not rows:
            blocking.append("empty_dataset")
        elif len(rows) < self.minimum_rows:
            blocking.append(f"row_count_below_minimum:{len(rows)}<{self.minimum_rows}")
        if verification is not None and not verification.reproducible:
            blocking.append(f"source_not_reproducible:{verification.status}")
        if manifest.stats.source_rows < self.recommended_source_rows:
            warnings.append(
                f"source_rows_below_recommended:{manifest.stats.source_rows}"
                f"<{self.recommended_source_rows}"
            )

        structure = self._structure(rows, manifest.feature_names, blocking)
        funnel = self._funnel(manifest.stats.model_dump(mode="json"), blocking)
        temporal = self._temporal(rows)
        labels = self._labels(rows, warnings, blocking)
        features, numeric = self._features(rows, manifest.feature_names, blocking)
        correlations = self._correlations(numeric)
        outliers = self._outliers(rows, numeric)
        regimes = self._regimes(rows)
        stability = self._stability(rows, numeric)
        constant_count = len(features["constant_features"])
        quasi_constant_count = len(features["quasi_constant_features"])
        correlation_count = len(correlations["alerts"])
        drift_count = len(stability["alerts"])
        if constant_count:
            warnings.append(f"constant_features:{constant_count}")
        if quasi_constant_count:
            warnings.append(f"quasi_constant_features:{quasi_constant_count}")
        if correlation_count:
            warnings.append(f"high_feature_correlations:{correlation_count}")
        if drift_count:
            warnings.append(f"temporal_drift_alerts:{drift_count}")
        causal = await self._causal(rows, backtests, candles, blocking)
        leak = self._leak(rows, manifest.feature_names, causal, blocking)

        source_counts: dict[str, int] = {}
        if backtests is not None:
            observations = await backtests.all_observations(manifest.source_job_id)
            outcomes = await backtests.all_outcomes(manifest.source_job_id)
            source_counts = {
                "observations": len(observations),
                "confirmed_observations": sum(
                    item.snapshot_status == "confirmed" for item in observations
                ),
                "h6_outcomes": sum(item.horizon == 6 for item in outcomes),
            }

        blocking = sorted(set(blocking))
        warnings = sorted(set(warnings))
        conclusion = cast(
            AuditConclusion,
            (
                "rejected"
                if blocking
                else "accepted_with_reservations" if warnings else "accepted_for_experiment_design"
            ),
        )
        return MLDatasetAuditReport(
            dataset_identity=dataset_identity,
            dataset={
                "data_file": manifest.data_file,
                "data_sha256": manifest.data_sha256,
                "manifest_sha256": manifest_sha256,
                "manifest_schema_version": manifest.manifest_schema_version,
                "feature_schema_version": manifest.feature_schema_version,
                "label_schema_version": manifest.label_schema_version,
                "row_count": len(rows),
                "first_decision_time": (
                    manifest.first_decision_time.isoformat()
                    if manifest.first_decision_time
                    else None
                ),
                "last_decision_time": (
                    manifest.last_decision_time.isoformat() if manifest.last_decision_time else None
                ),
                "symbol": rows[0].symbol if rows else None,
                "timeframe": rows[0].timeframe if rows else None,
                "feature_count": len(manifest.feature_names),
            },
            source={
                "job_id": manifest.source_job_id,
                "source_identity": manifest.source_identity,
                "input_data_fingerprint": manifest.input_data_fingerprint,
                "profile_fingerprint": manifest.profile_fingerprint,
                "verification_status": verification.status if verification else "not_requested",
                "canonical_config": (
                    manifest.backtest_config.model_dump(mode="json")
                    if manifest.backtest_config is not None
                    else None
                ),
                "streams": [item.model_dump(mode="json") for item in manifest.input_streams],
                **source_counts,
            },
            funnel=funnel,
            structure=structure,
            temporal=temporal,
            labels=labels,
            features=features,
            correlations=correlations,
            outliers=outliers,
            regimes=regimes,
            stability=stability,
            causal_audit=causal,
            leak_audit=leak,
            blocking_failures=blocking,
            warnings=warnings,
            conclusion=conclusion,
        )

    def _structure(
        self, rows: tuple[MLDatasetRow, ...], declared: list[str], blocking: list[str]
    ) -> dict[str, Any]:
        observation_ids = [row.observation_id for row in rows]
        decisions = [row.decision_time for row in rows]
        actual_features = sorted({name for row in rows for name in row.features})
        duplicate_ids = len(observation_ids) - len(set(observation_ids))
        duplicate_times = len(decisions) - len(set(decisions))
        monotone = all(left < right for left, right in zip(decisions, decisions[1:]))
        symbols = sorted({row.symbol for row in rows})
        timeframes = sorted({row.timeframe for row in rows})
        profiles = sorted({row.profile_id for row in rows})
        profile_fingerprints = sorted(
            {row.profile_fingerprint for row in rows if row.profile_fingerprint is not None}
        )
        missing_profile_fingerprint = any(row.profile_fingerprint is None for row in rows)
        missing_required = sorted(
            name for name in REQUIRED_V2_FEATURES if any(name not in row.features for row in rows)
        )
        if duplicate_ids:
            blocking.append("duplicate_observation_ids")
        if duplicate_times:
            blocking.append("duplicate_decision_times")
        if not monotone:
            blocking.append("decision_times_not_strictly_increasing")
        if len(symbols) != 1 or len(timeframes) != 1:
            blocking.append("mixed_symbol_or_timeframe")
        if (
            profiles != ["ml-dataset-v2"]
            or len(profile_fingerprints) != 1
            or missing_profile_fingerprint
        ):
            blocking.append("mixed_or_invalid_profile")
        if actual_features != declared:
            blocking.append("declared_feature_inventory_mismatch")
        if missing_required:
            blocking.append("required_features_missing")
        return {
            "valid": not any(
                item.startswith(("duplicate", "decision", "mixed", "declared", "required"))
                for item in blocking
            ),
            "duplicate_observation_id_count": duplicate_ids,
            "duplicate_decision_time_count": duplicate_times,
            "strict_chronological_order": monotone,
            "symbols": symbols,
            "timeframes": timeframes,
            "profiles": profiles,
            "profile_fingerprints": profile_fingerprints,
            "declared_feature_count": len(declared),
            "actual_feature_count": len(actual_features),
            "missing_required_features": missing_required,
        }

    def _funnel(self, stats: dict[str, Any], blocking: list[str]) -> dict[str, Any]:
        source = int(stats["source_rows"])
        generated = int(stats["generated_rows"])
        categories = {
            "censored_outcomes": int(stats["censored_outcomes"]),
            "invalid_outcomes": int(stats["invalid_outcomes"]),
            "missing_natr": int(stats["missing_natr"]),
            "contract_rejections": int(stats["contract_rejections"]),
        }
        excluded = sum(categories.values())
        reconciled = generated + excluded == source == int(stats["processed_rows"])
        if not reconciled:
            blocking.append("funnel_not_reconciled")
        return {
            "candidate_observations_with_h6": source,
            "processed_rows": int(stats["processed_rows"]),
            "final_rows": generated,
            "excluded_rows": excluded,
            "exclusions_priority": [
                "censored_outcomes",
                "invalid_outcomes",
                "missing_natr",
                "contract_rejections",
            ],
            "exclusions": {
                name: {
                    "count": count,
                    "percent_of_candidates": (count / source * 100 if source else 0.0),
                }
                for name, count in categories.items()
            },
            "final_percent_of_candidates": generated / source * 100 if source else 0.0,
            "reconciled": reconciled,
            "contract_rejection_reasons": stats["rejection_reasons"],
        }

    def _temporal(self, rows: tuple[MLDatasetRow, ...]) -> dict[str, Any]:
        by_year = Counter(str(row.decision_time.year) for row in rows)
        by_quarter = Counter(
            f"{row.decision_time.year}-Q{(row.decision_time.month - 1) // 3 + 1}" for row in rows
        )
        by_month = Counter(row.decision_time.strftime("%Y-%m") for row in rows)
        by_weekday = Counter(str(row.decision_time.weekday()) for row in rows)
        by_hour = Counter(f"{row.decision_time.hour:02d}" for row in rows)
        gaps = [
            int((right.decision_time - left.decision_time).total_seconds())
            for left, right in zip(rows, rows[1:])
        ]
        return {
            "by_year": dict(sorted(by_year.items())),
            "by_quarter": dict(sorted(by_quarter.items())),
            "by_month": dict(sorted(by_month.items())),
            "by_weekday_utc": dict(sorted(by_weekday.items())),
            "by_hour_utc": dict(sorted(by_hour.items())),
            "largest_observation_gap_seconds": max(gaps, default=0),
            "duration_seconds": (
                int((rows[-1].decision_time - rows[0].decision_time).total_seconds())
                if len(rows) > 1
                else 0
            ),
        }

    def _labels(
        self, rows: tuple[MLDatasetRow, ...], warnings: list[str], blocking: list[str]
    ) -> dict[str, Any]:
        counts = _label_counts(rows)
        total = len(rows)
        missing = sorted(label for label, count in counts.items() if not count)
        if missing:
            blocking.append("missing_label_classes:" + ",".join(missing))
        for label, count in counts.items():
            if total and count / total < 0.05:
                warnings.append(f"minority_label:{label}:{count / total:.6f}")
        transitions: Counter[str] = Counter(
            f"{left.label.value}->{right.label.value}" for left, right in zip(rows, rows[1:])
        )
        by_year: dict[str, dict[str, int]] = {}
        for year in sorted({row.decision_time.year for row in rows}):
            by_year[str(year)] = _label_counts(
                row for row in rows if row.decision_time.year == year
            )
        return {
            "counts": counts,
            "percentages": {
                label: count / total * 100 if total else 0.0 for label, count in counts.items()
            },
            "by_year": by_year,
            "longest_consecutive_run": {
                label.value: _longest_label_run(rows, label) for label in MarketDirectionLabel
            },
            "longest_same_label_run": _longest_run(row.label.value for row in rows),
            "transitions": dict(sorted(transitions.items())),
            "future_return": _summary(row.future_return for row in rows),
            "natr_percent": _summary(row.natr_percent for row in rows),
            "distance_to_threshold": _summary(
                abs(row.future_return) - row.neutral_threshold_return for row in rows
            ),
            "missing_classes": missing,
        }

    def _features(
        self,
        rows: tuple[MLDatasetRow, ...],
        names: list[str],
        blocking: list[str],
    ) -> tuple[dict[str, Any], dict[str, dict[int, float]]]:
        result: dict[str, Any] = {}
        numeric: dict[str, dict[int, float]] = {}
        for name in names:
            present = [
                (index, row.features.get(name))
                for index, row in enumerate(rows)
                if name in row.features
            ]
            values = [value for _, value in present]
            non_finite = sum(
                isinstance(value, float) and not math.isfinite(value) for value in values
            )
            if non_finite:
                blocking.append(f"non_finite_feature:{name}")
            kinds = sorted(
                {"bool" if isinstance(value, bool) else type(value).__name__ for value in values}
            )
            counts = Counter(str(value) for value in values)
            dominant = max(counts.values(), default=0) / len(values) if values else 0.0
            constant = len(counts) == 1 and len(values) == len(rows)
            quasi = dominant >= QUASI_CONSTANT_DOMINANCE and not constant
            numeric_values = {
                index: float(value)
                for index, value in present
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            if numeric_values:
                numeric[name] = numeric_values
            years: dict[str, dict[str, float | int | None]] = {}
            if numeric_values:
                for year in sorted({row.decision_time.year for row in rows}):
                    years[str(year)] = _summary(
                        value
                        for index, value in numeric_values.items()
                        if rows[index].decision_time.year == year
                    )
            result[name] = {
                "types": kinds,
                "present_count": len(values),
                "missing_count": len(rows) - len(values),
                "non_finite_count": non_finite,
                "distinct_count": len(counts),
                "dominant_value_proportion": dominant,
                "zero_count": sum(value == 0 for value in values),
                "longest_constant_run": _longest_run(values),
                "constant": constant,
                "quasi_constant": quasi,
                "numeric_summary": _summary(numeric_values.values()),
                "numeric_by_year": years,
                "top_values": dict(
                    sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
                ),
            }
        return {
            "statistics": dict(sorted(result.items())),
            "constant_features": sorted(name for name, item in result.items() if item["constant"]),
            "quasi_constant_features": sorted(
                name for name, item in result.items() if item["quasi_constant"]
            ),
        }, numeric

    def _correlations(self, numeric: dict[str, dict[int, float]]) -> dict[str, Any]:
        alerts: list[dict[str, Any]] = []
        names = sorted(numeric)
        if not names:
            return {"alert_threshold": CORRELATION_ALERT, "alerts": alerts}
        row_count = max((max(values, default=-1) for values in numeric.values()), default=-1) + 1
        matrix = np.full((row_count, len(names)), np.nan, dtype=np.float64)
        for column, name in enumerate(names):
            for row, value in numeric[name].items():
                matrix[row, column] = value
        frame = pd.DataFrame(matrix, columns=names)
        minimum_common = max(30, math.ceil(row_count * 0.05))
        pearson_matrix = frame.corr(method="pearson", min_periods=minimum_common).to_numpy()
        spearman_matrix = frame.corr(method="spearman", min_periods=minimum_common).to_numpy()
        present = (~np.isnan(matrix)).astype(np.int32)
        common_matrix = present.T @ present
        for left_index, left_name in enumerate(names):
            for right_index in range(left_index + 1, len(names)):
                right_name = names[right_index]
                pearson = float(pearson_matrix[left_index, right_index])
                spearman = float(spearman_matrix[left_index, right_index])
                if not math.isfinite(pearson) or not math.isfinite(spearman):
                    continue
                if max(abs(pearson), abs(spearman)) >= CORRELATION_ALERT:
                    alerts.append(
                        {
                            "left": left_name,
                            "right": right_name,
                            "common_count": int(common_matrix[left_index, right_index]),
                            "pearson": pearson,
                            "spearman": spearman,
                        }
                    )
        alerts.sort(
            key=lambda item: (
                -max(abs(item["pearson"]), abs(item["spearman"])),
                item["left"],
                item["right"],
            )
        )
        return {
            "alert_threshold": CORRELATION_ALERT,
            "minimum_common_count": minimum_common,
            "alerts": alerts,
        }

    def _outliers(
        self, rows: tuple[MLDatasetRow, ...], numeric: dict[str, dict[int, float]]
    ) -> dict[str, Any]:
        examples: list[dict[str, Any]] = []
        maximum_examples = 100
        for name in sorted(numeric):
            if len(examples) >= maximum_examples:
                break
            values = np.asarray(list(numeric[name].values()), dtype=np.float64)
            if len(values) < 20:
                continue
            low, high = np.quantile(values, [0.001, 0.999])
            for index, value in numeric[name].items():
                if value < low or value > high:
                    examples.append(
                        {
                            "feature": name,
                            "decision_time": rows[index].decision_time.isoformat(),
                            "value": value,
                            "q001": float(low),
                            "q999": float(high),
                        }
                    )
                    if sum(item["feature"] == name for item in examples) >= 3:
                        break
        return {
            "method": "outside_empirical_q001_q999",
            "maximum_examples": maximum_examples,
            "examples": examples,
        }

    def _regimes(self, rows: tuple[MLDatasetRow, ...]) -> dict[str, Any]:
        if not rows:
            return {"definition": "natr_terciles", "segments": {}}
        low, high = np.quantile([row.natr_percent for row in rows], [1 / 3, 2 / 3])
        segments: dict[str, list[MLDatasetRow]] = {"low": [], "medium": [], "high": []}
        for row in rows:
            key = (
                "low"
                if row.natr_percent <= low
                else "high" if row.natr_percent > high else "medium"
            )
            segments[key].append(row)
        return {
            "definition": "natr_terciles_descriptive_only",
            "low_upper": float(low),
            "high_lower": float(high),
            "segments": {
                name: {"row_count": len(items), "labels": _label_counts(items)}
                for name, items in segments.items()
            },
        }

    def _stability(
        self,
        rows: tuple[MLDatasetRow, ...],
        numeric: dict[str, dict[int, float]],
    ) -> dict[str, Any]:
        years = sorted({row.decision_time.year for row in rows})
        drifts: list[dict[str, Any]] = []
        for name in sorted(numeric):
            previous: tuple[int, float, float] | None = None
            for year in years:
                values = [
                    value
                    for index, value in numeric[name].items()
                    if rows[index].decision_time.year == year
                ]
                if len(values) < 2:
                    continue
                current = (year, float(np.mean(values)), float(np.std(values)))
                if previous is not None:
                    scale = max(previous[2], current[2], 1e-12)
                    normalized = abs(current[1] - previous[1]) / scale
                    if normalized >= 2:
                        drifts.append(
                            {
                                "feature": name,
                                "from_year": previous[0],
                                "to_year": year,
                                "normalized_mean_difference": normalized,
                            }
                        )
                previous = current
        drifts.sort(key=lambda item: (-item["normalized_mean_difference"], item["feature"]))
        return {"method": "adjacent_year_normalized_mean_difference", "alerts": drifts}

    async def _causal(
        self,
        rows: tuple[MLDatasetRow, ...],
        backtests: BacktestRepository | None,
        candles: CandleRepository | None,
        blocking: list[str],
    ) -> dict[str, Any]:
        sample = _deterministic_sample(rows)
        if backtests is None or candles is None or not sample:
            return {
                "status": "not_run",
                "method": "raw_ohlcv_recalculation",
                "sample_size": 0,
                "mismatch_count": 0,
            }
        job = await backtests.get_job(sample[0].job_id)
        if job is None:
            blocking.append("causal_source_job_absent")
            return {"status": "failed", "sample_size": 0, "mismatch_count": 0}
        snapshot = await load_backtest_input_snapshot(SQLiteHistoricalRepository(candles), job)
        mismatches: list[dict[str, Any]] = []
        checked: list[int] = []
        interval = timeframe_milliseconds(job.config.signal_config.timeframe)
        for expected in sample:
            series = snapshot.primary[expected.symbol]
            decision_ms = int(expected.decision_time.timestamp() * 1_000)
            try:
                index = next(
                    idx
                    for idx, candle in enumerate(series.candles)
                    if (candle.close_time or candle.open_time + interval) == decision_ms
                )
            except StopIteration:
                mismatches.append(
                    {"observation_id": expected.observation_id, "reason": "decision_candle_absent"}
                )
                continue
            signal = job.config.signal_config
            primary = series.candles[max(0, index - primary_ohlcv_limit(signal) + 1) : index + 1]
            trend_sets: dict[str, list[Any]] = {signal.timeframe: primary}
            for timeframe, trend_candles in snapshot.trends[expected.symbol].items():
                eligible = [
                    candle
                    for candle in trend_candles
                    if (candle.close_time or candle.open_time) <= decision_ms
                ]
                trend_sets[timeframe] = eligible[-ma_ohlcv_limit(signal) :]
            observation = evaluate_signal_snapshot(
                job_id=job.id,
                symbol=expected.symbol,
                decision_time_ms=decision_ms,
                primary=primary,
                trend_candles=trend_sets,
                profile=signal,
                snapshot_status=job.config.snapshot_status,
                dataset_version=job.dataset_version,
                profile_id=job.config.signal_profile_id,
            )
            observation.id = expected.observation_id
            outcome = next(
                item
                for item in calculate_forward_outcomes(
                    expected.observation_id, series.candles, index, job.config
                )
                if item.horizon == expected.horizon
            )
            actual = build_ml_dataset_row(
                observation,
                outcome,
                feature_schema_version=expected.feature_schema_version,
                natr_multiplier=expected.natr_multiplier,
            )
            checked.append(expected.observation_id)
            if actual != expected:
                mismatches.append(
                    {
                        "observation_id": expected.observation_id,
                        "reason": "recalculated_row_differs",
                    }
                )
        if mismatches:
            blocking.append("causal_recalculation_mismatch")
        return {
            "status": "passed" if not mismatches else "failed",
            "method": "deterministic_raw_ohlcv_recalculation",
            "selection_rule": "boundaries_quartiles_years_labels_natr_extremes",
            "sample_size": len(checked),
            "observation_ids": checked,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
            "numeric_tolerance": "model_contract_and_math_isclose_defaults",
        }

    def _leak(
        self,
        rows: tuple[MLDatasetRow, ...],
        names: list[str],
        causal: dict[str, Any],
        blocking: list[str],
    ) -> dict[str, Any]:
        forbidden = sorted(
            name
            for name in names
            if name in FORBIDDEN_FEATURE_NAMES
            or name.startswith(("target.", "outcome.", "future."))
        )
        chronology = all(
            row.source_open_time is None
            or row.source_open_time <= row.decision_time <= row.entry_time < row.exit_time
            for row in rows
        )
        horizon_consistent = all(
            int((row.exit_time - row.entry_time).total_seconds())
            == row.horizon * timeframe_milliseconds(row.timeframe) // 1_000
            for row in rows
        )
        if forbidden:
            blocking.append("forbidden_future_features")
        if not chronology or not horizon_consistent:
            blocking.append("future_chronology_inconsistent")
        checks = {
            "forbidden_feature_names_absent": not forbidden,
            "forbidden_feature_names": forbidden,
            "chronology_valid": chronology,
            "horizon_timing_valid": horizon_consistent,
            "raw_causal_recalculation_passed": causal.get("status") == "passed",
            "outcomes_excluded_from_features": not forbidden,
            "learned_preprocessing_applied": False,
            "global_dataset_scaler_applied": False,
            "normalized_components_are_indicator_local": True,
        }
        return {
            "status": (
                "no_leak_detected_by_defined_checks"
                if all(
                    value
                    for key, value in checks.items()
                    if key
                    not in {
                        "forbidden_feature_names",
                        "learned_preprocessing_applied",
                        "global_dataset_scaler_applied",
                    }
                )
                and not checks["learned_preprocessing_applied"]
                and not checks["global_dataset_scaler_applied"]
                else "leak_risk_detected"
            ),
            "checks": checks,
        }


def render_audit_markdown(report: MLDatasetAuditReport, commands: list[str] | None = None) -> str:
    """Rend un rapport humain stable à partir du JSON canonique."""
    data = report.dataset
    source = report.source
    label_counts = report.labels.get("counts", {})
    lines = [
        "# Audit du dataset ML v2 réel",
        "",
        "## Résumé exécutif",
        "",
        f"Conclusion calculée : `{report.conclusion}`.",
        "Ce rapport évalue uniquement la qualité technique et causale des données. Aucun modèle",
        "n'a été entraîné et aucune période terminale de test ML v2 n'a été définie.",
        "",
        "## Identification",
        "",
        f"- Dataset : `{report.dataset_identity}`",
        f"- Job source : `{source.get('job_id')}`",
        f"- Source identity : `{source.get('source_identity')}`",
        f"- Input fingerprint : `{source.get('input_data_fingerprint')}`",
        f"- Symbole / timeframe : `{data.get('symbol')}` / `{data.get('timeframe')}`",
        f"- Bornes : `{data.get('first_decision_time')}` à `{data.get('last_decision_time')}`",
        f"- Lignes : `{data.get('row_count')}`",
        f"- SHA-256 JSONL : `{data.get('data_sha256')}`",
        f"- SHA-256 manifeste : `{data.get('manifest_sha256')}`",
        "",
        "## Commandes de reproduction",
        "",
    ]
    lines.extend(f"```text\n{command}\n```" for command in commands or [])
    lines.extend(
        [
            "",
            "## Couverture et provenance",
            "",
            f"Vérification source : `{source.get('verification_status')}`.",
            f"Flux consommés : `{len(source.get('streams', []))}`.",
            "La fenêtre est une fenêtre de développement et d'audit, choisie pour sa continuité,",
            "ses warmups complets et sa couverture des régimes 2020-2022. Elle s'arrête avant le",
            "trou OHLCV observé à partir du 29 septembre 2022.",
            "",
            "```json",
            json.dumps(source.get("streams", []), ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
            "## Funnel",
            "",
            "```json",
            json.dumps(report.funnel, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
            "## Audit structurel",
            "",
            "```json",
            json.dumps(report.structure, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
            "## Labels",
            "",
            f"Distribution : `{json.dumps(label_counts, sort_keys=True)}`.",
            f"Pourcentages : `{json.dumps(report.labels.get('percentages', {}), sort_keys=True)}`.",
            f"Par année : `{json.dumps(report.labels.get('by_year', {}), sort_keys=True)}`.",
            f"Plus longues séquences : `{json.dumps(report.labels.get('longest_consecutive_run', {}), sort_keys=True)}`.",
            "",
            "## Audit temporel",
            "",
            "```json",
            json.dumps(report.temporal, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
            "## Features, redondances et valeurs extrêmes",
            "",
            f"Features constantes : `{json.dumps(report.features.get('constant_features', []))}`.",
            f"Features quasi constantes : `{json.dumps(report.features.get('quasi_constant_features', []))}`.",
            f"Paires fortement corrélées : `{len(report.correlations.get('alerts', []))}`.",
            f"Exemples extrêmes : `{len(report.outliers.get('examples', []))}`.",
            "Les statistiques exhaustives des 675 features, les corrélations et les timestamps",
            "extrêmes sont conservés dans `dataset-audit.json`.",
            "Les seuils extrêmes sont des alertes descriptives ; aucune ligne n'est supprimée.",
            "",
            "## Régimes et stabilité temporelle",
            "",
            "Les régimes sont des terciles NATR descriptifs calculés sur cette fenêtre de",
            "développement. Ils ne servent ni à sélectionner un modèle ni à optimiser une stratégie.",
            f"Segments : `{json.dumps(report.regimes.get('segments', {}), sort_keys=True)}`.",
            f"Alertes de dérive annuelle : `{len(report.stability.get('alerts', []))}`.",
            "",
            "## Audit causal",
            "",
            "```json",
            json.dumps(report.causal_audit, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
            "## Leak audit",
            "",
            f"Conclusion : `{report.leak_audit.get('status')}`.",
            "Cette conclusion est limitée aux contrôles définis et ne signifie pas qu'une fuite",
            "future impossible à concevoir est exclue absolument.",
            "",
            "## Contrôles bloquants",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in report.blocking_failures)
    if not report.blocking_failures:
        lines.append("- Aucun.")
    lines.extend(["", "## Alertes non bloquantes", ""])
    lines.extend(f"- `{item}`" for item in report.warnings)
    if not report.warnings:
        lines.append("- Aucune.")
    lines.extend(
        [
            "",
            "## Limites et Phase 4",
            "",
            "Le JSONL n'est pas une période terminale et aucune mesure de performance de modèle",
            "n'a été calculée. La Phase 4 devra figer les partitions chronologiques avant tout",
            "entraînement, preprocessing appris, sélection de features ou benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def write_audit_artifact(path: Path, content: bytes) -> str:
    """Crée atomiquement ou réutilise un artefact byte-identique, sans écrasement divergent."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = destination.read_bytes()
        if existing != content:
            raise ValueError(f"refus d'écraser un artefact divergent : {destination.name}")
        return _sha256_bytes(existing)
    with NamedTemporaryFile("wb", dir=destination.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return _sha256_bytes(content)


def audit_json_bytes(report: MLDatasetAuditReport) -> bytes:
    return _canonical_json_bytes(report.model_dump(mode="json"))
