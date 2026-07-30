"""Expérience isolée Phase 7.2 sur le seul verdict du filtre RSI.

Ce module réutilise des observations canoniques et ne recalcule aucun
indicateur par variante. Il n'est importé par aucun chemin de production.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import math
import pickle
import statistics
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast

from app.audits.signal_strategy_baseline import (
    BASELINE_VERSION,
    DatasetSelection,
    ReadOnlyHistoricalRepository,
    _extended_metrics,
    _jsonable,
    chronological_segments,
    inventory_datasets,
    order_diagnostics,
    profit_concentration,
    select_datasets,
    stable_fingerprint,
)
from app.core.settings import ScanConfig, Timeframe
from app.database.connection import Database
from app.domain.portfolio import (
    PortfolioSimulationConfig,
    PortfolioSimulationResult,
    PortfolioSimulationStep,
    SimulatedTrade,
    simulate_portfolio,
)
from app.models.backtest import (
    BacktestConfig,
    BacktestJob,
    BacktestStatus,
    ForwardOutcome,
    SignalObservation,
)
from app.models.portfolio import PortfolioSimulationConfigV1
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.services.backtest_engine import BacktestEngine
from app.services.portfolio_replay import build_portfolio_simulation_steps

VERSION = "rsi-filter-experiment-v1"
BASELINE_FINGERPRINT = "sha256:7a35c7442778828cd207b6fbaee4a6d8390d6bb8fcb7d79751030d433b44a1b6"
BASELINE_COUNTS = {
    "candles": 12_973,
    "observations": 12_973,
    "accepted": 33,
    "false_to_true": 22,
    "true_to_false": 22,
    "orders": 44,
    "executed_orders": 44,
    "rejected_orders": 0,
    "trades": 22,
}
STAGE_SEGMENTS = {
    "development": "development",
    "validation": "validation",
    "final-test": "test",
}
VARIANT_ORDER = ("R0", "R1", "R2", "R3")
MANIFEST_MARKER = "<!-- rsi-filter-experiment-v1-manifest -->"


class ExperimentInvalidated(RuntimeError):
    """Violation d'un invariant préenregistré."""


@dataclass(frozen=True, slots=True)
class VariantSpec:
    id: str
    delta: Decimal | None
    threshold: Decimal | None
    operator: str | None
    diagnostic_control: bool = False


VARIANTS: dict[str, VariantSpec] = {
    "R0": VariantSpec("R0", Decimal("0"), Decimal("35"), "<"),
    "R1": VariantSpec("R1", Decimal("5"), Decimal("40"), "<"),
    "R2": VariantSpec("R2", Decimal("10"), Decimal("45"), "<"),
    "R3": VariantSpec("R3", None, None, None, diagnostic_control=True),
}


@dataclass(frozen=True, slots=True)
class PreparedDataset:
    selection: DatasetSelection
    observations: tuple[SignalObservation, ...]
    outcomes: tuple[ForwardOutcome, ...]
    steps: tuple[PortfolioSimulationStep, ...]
    portfolio_config: PortfolioSimulationConfig

    @property
    def key(self) -> str:
        return self.selection.key


def manifest_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if MANIFEST_MARKER not in text:
        raise ExperimentInvalidated("marqueur de manifeste absent")
    remainder = text.split(MANIFEST_MARKER, 1)[1]
    try:
        block = remainder.split("```json", 1)[1].split("```", 1)[0]
        payload = json.loads(block)
    except (IndexError, json.JSONDecodeError) as exc:
        raise ExperimentInvalidated("bloc JSON du manifeste invalide") from exc
    validate_manifest(payload)
    return cast(dict[str, Any], payload)


def validate_manifest(payload: Mapping[str, Any]) -> None:
    if payload.get("version") != VERSION:
        raise ExperimentInvalidated("version de manifeste inconnue")
    baseline = payload.get("baseline")
    if not isinstance(baseline, Mapping) or baseline.get("version") != BASELINE_VERSION:
        raise ExperimentInvalidated("baseline absente ou inconnue")
    if baseline.get("fingerprint") != BASELINE_FINGERPRINT:
        raise ExperimentInvalidated("fingerprint baseline modifié")
    variants = payload.get("variants")
    if not isinstance(variants, list) or [item.get("id") for item in variants] != list(
        VARIANT_ORDER
    ):
        raise ExperimentInvalidated("variantes préenregistrées modifiées")
    for raw, expected in zip(variants, VARIANTS.values(), strict=True):
        threshold = raw.get("threshold")
        delta = raw.get("delta")
        if (Decimal(threshold) if threshold is not None else None) != expected.threshold:
            raise ExperimentInvalidated(f"seuil {expected.id} modifié")
        if (Decimal(delta) if delta is not None else None) != expected.delta:
            raise ExperimentInvalidated(f"delta {expected.id} modifié")
        if raw.get("operator") != expected.operator:
            raise ExperimentInvalidated(f"opérateur {expected.id} modifié")
    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or len(datasets) != 5:
        raise ExperimentInvalidated("datasets gelés absents")
    for item in datasets:
        if not isinstance(item, Mapping):
            raise ExperimentInvalidated("dataset invalide")
        segments = item.get("segments")
        if not isinstance(segments, Mapping) or set(segments) != {
            "development",
            "validation",
            "test",
        }:
            raise ExperimentInvalidated("segments gelés invalides")
        expected_start = 0
        for name in ("development", "validation", "test"):
            bounds = segments[name]
            if not isinstance(bounds, Mapping) or bounds.get("start_index") != expected_start:
                raise ExperimentInvalidated("segments non contigus")
            expected_start = int(bounds["end_index"])
        if expected_start != item.get("candles"):
            raise ExperimentInvalidated("segment final différent du dataset")


def relax_threshold(operator: str, threshold: Decimal, delta: Decimal) -> Decimal:
    """Élargit mécaniquement un prédicat unilatéral et clamp entre 0 et 100."""
    if operator in {"<", "<="}:
        return min(Decimal("100"), threshold + delta)
    if operator in {">", ">="}:
        return max(Decimal("0"), threshold - delta)
    raise ValueError(f"opérateur RSI non pris en charge: {operator}")


def _rsi_status(observation: SignalObservation) -> str:
    signal = observation.indicator_signals.get("rsi")
    if signal is not None:
        return str(getattr(signal.status, "value", signal.status))
    return str(observation.availability.get("rsi", "insufficient_data"))


def rsi_filter_passes(observation: SignalObservation, variant: VariantSpec) -> bool:
    """Applique uniquement le verdict de valeur, sans inventer de disponibilité."""
    value = observation.rsi
    if _rsi_status(observation) != "available" or value is None or not math.isfinite(value):
        return False
    if variant.diagnostic_control:
        return True
    assert variant.threshold is not None and variant.operator is not None
    decimal_value = Decimal(str(value))
    if variant.operator == "<":
        return decimal_value < variant.threshold
    if variant.operator == "<=":
        return decimal_value <= variant.threshold
    if variant.operator == ">":
        return decimal_value > variant.threshold
    if variant.operator == ">=":
        return decimal_value >= variant.threshold
    raise ExperimentInvalidated("opérateur RSI inconnu")


def counterfactual_filter_matrix(
    observation: SignalObservation, variant: VariantSpec
) -> dict[str, bool]:
    """Évalue tous les verdicts indépendamment, sans court-circuit."""
    matrix = {
        str(item["stage"]): bool(item["passed"])
        for item in observation.filter_trace
        if "stage" in item and "passed" in item
    }
    required = {"rsi", "trend", "signal_filters", "confluence"}
    if set(matrix) != required:
        raise ExperimentInvalidated(
            f"trace de filtres incomplète pour observation {observation.id}: {sorted(matrix)}"
        )
    matrix["rsi"] = rsi_filter_passes(observation, variant)
    return matrix


def apply_variant(observation: SignalObservation, variant: VariantSpec) -> SignalObservation:
    """Clone une observation en ne modifiant que le verdict et sa trace RSI."""
    matrix = counterfactual_filter_matrix(observation, variant)
    reasons = {
        "rsi": "rsi_indisponible_ou_seuil",
        "trend": "tendance_sous_seuil",
        "signal_filters": "classe_non_autorisee",
        "confluence": "confluence_indisponible_ou_sous_seuil",
    }
    order = ("rsi", "trend", "signal_filters", "confluence")
    failure = next((stage for stage in order if not matrix[stage]), None)
    trace = [
        {
            "stage": stage,
            "passed": matrix[stage],
            "reason": None if matrix[stage] else reasons[stage],
        }
        for stage in order
    ]
    return observation.model_copy(
        update={
            "accepted": failure is None,
            "rejection_stage": failure,
            "rejection_reason": reasons[failure] if failure else None,
            "filter_trace": trace,
        },
        deep=True,
    )


def assert_variant_invariants(
    canonical: Sequence[SignalObservation],
    variants: Mapping[str, Sequence[SignalObservation]],
) -> None:
    """Verrouille parité R0, monotonie et identité de toutes les entrées."""
    if len(variants.get("R0", ())) != len(canonical):
        raise ExperimentInvalidated("taille R0 différente de la production")
    immutable_fields = (
        "rsi",
        "close",
        "trend_score",
        "trend_states",
        "macd_signal",
        "bollinger_position",
        "stochastic_signal",
        "confluence_score",
        "confluence_grade",
        "confluence_factors",
        "availability",
        "indicator_signals",
        "raw_values",
        "classes",
        "profile_fingerprint",
    )
    for index, original in enumerate(canonical):
        r0 = variants["R0"][index]
        if (
            r0.accepted != original.accepted
            or r0.rejection_stage != original.rejection_stage
            or r0.rejection_reason != original.rejection_reason
            or r0.filter_trace != original.filter_trace
        ):
            raise ExperimentInvalidated(f"divergence R0 observation {original.id}")
        if all(name in variants for name in ("R0", "R1", "R2")):
            decisions = [variants[name][index].accepted for name in ("R0", "R1", "R2")]
            if (decisions[0] and not decisions[1]) or (decisions[1] and not decisions[2]):
                raise ExperimentInvalidated(f"monotonie RSI violée observation {original.id}")
        for name in variants:
            candidate = variants[name][index]
            for field in immutable_fields:
                if getattr(candidate, field) != getattr(original, field):
                    raise ExperimentInvalidated(
                        f"{field} modifié par {name} observation {original.id}"
                    )


def _variant_steps(
    steps: Sequence[PortfolioSimulationStep],
    observations: Sequence[SignalObservation],
) -> tuple[PortfolioSimulationStep, ...]:
    if len(steps) != len(observations):
        raise ExperimentInvalidated("désalignement observations/bougies")
    return tuple(
        replace(step, accepted=observation.accepted)
        for step, observation in zip(steps, observations, strict=True)
    )


def _distribution(values: Iterable[Decimal]) -> dict[str, Any]:
    items = sorted(values)
    if not items:
        return {"count": 0}

    def quantile(ratio: Decimal) -> Decimal:
        return items[int((len(items) - 1) * ratio)]

    return {
        "count": len(items),
        "minimum": items[0],
        "q10": quantile(Decimal("0.10")),
        "q25": quantile(Decimal("0.25")),
        "median": Decimal(str(statistics.median(items))),
        "q75": quantile(Decimal("0.75")),
        "q90": quantile(Decimal("0.90")),
        "maximum": items[-1],
    }


def _transitions(observations: Sequence[SignalObservation]) -> tuple[int, int]:
    up = sum(
        not previous.accepted and current.accepted
        for previous, current in zip(observations, observations[1:])
    )
    down = sum(
        previous.accepted and not current.accepted
        for previous, current in zip(observations, observations[1:])
    )
    return up, down


def _accepted_sequences(observations: Sequence[SignalObservation]) -> dict[str, Any]:
    lengths: list[Decimal] = []
    current = 0
    for item in observations:
        if item.accepted:
            current += 1
        elif current:
            lengths.append(Decimal(current))
            current = 0
    if current:
        lengths.append(Decimal(current))
    result = _distribution(lengths)
    result["sequence_count"] = len(lengths)
    return result


def _funnel(observations: Sequence[SignalObservation], variant: VariantSpec) -> dict[str, Any]:
    matrices = [counterfactual_filter_matrix(item, variant) for item in observations]
    rsi_available = sum(
        _rsi_status(item) == "available" and item.rsi is not None and math.isfinite(item.rsi)
        for item in observations
    )
    rsi_insufficient = sum(_rsi_status(item) == "insufficient_data" for item in observations)
    rsi_invalid = sum(_rsi_status(item) == "invalid_data" for item in observations)
    rsi_pass = sum(item["rsi"] for item in matrices)
    all_non_rsi = sum(
        all(item[stage] for stage in ("trend", "signal_filters", "confluence")) for item in matrices
    )
    accepted = sum(item.accepted for item in observations)
    up, down = _transitions(observations)
    first_rejections = Counter(item.rejection_stage or "none" for item in observations)
    overlaps: Counter[str] = Counter()
    for matrix in matrices:
        if matrix["rsi"]:
            continue
        failed = [stage for stage in ("trend", "signal_filters", "confluence") if not matrix[stage]]
        if not failed:
            overlaps["rsi_only"] += 1
        elif len(failed) == 1:
            overlaps[f"rsi+{failed[0]}"] += 1
        else:
            overlaps["rsi+multiple"] += 1
    return {
        "observations": len(observations),
        "rsi_available": rsi_available,
        "rsi_insufficient": rsi_insufficient,
        "rsi_invalid": rsi_invalid,
        "rsi_pass": rsi_pass,
        "rsi_fail": len(observations) - rsi_pass,
        "all_non_rsi_pass": all_non_rsi,
        "rsi_only_rejections": overlaps["rsi_only"],
        "accepted": accepted,
        "rejected": len(observations) - accepted,
        "false_to_true": up,
        "true_to_false": down,
        "first_rejection_stages": dict(first_rejections),
        "rejection_overlaps": dict(overlaps),
        "accepted_sequences": _accepted_sequences(observations),
    }


def _trade_key(trade: SimulatedTrade) -> tuple[str, str | None, str]:
    return (
        trade.entry_observation_id,
        trade.exit_observation_id,
        str(getattr(trade.exit_reason, "value", trade.exit_reason)),
    )


def _trade_comparison(
    baseline: PortfolioSimulationResult,
    candidate: PortfolioSimulationResult,
    observations: Sequence[SignalObservation],
    variant: VariantSpec,
) -> dict[str, Any]:
    baseline_by_key = {_trade_key(item): item for item in baseline.trades}
    candidate_by_key = {_trade_key(item): item for item in candidate.trades}
    observation_by_id = {str(item.id): item for item in observations}
    common = sorted(set(baseline_by_key) & set(candidate_by_key))
    added = sorted(set(candidate_by_key) - set(baseline_by_key))
    removed = sorted(set(baseline_by_key) - set(candidate_by_key))
    provenance = []
    for key in added:
        trade = candidate_by_key[key]
        entry = observation_by_id.get(trade.entry_observation_id)
        provenance.append(
            {
                "entry_observation_id": trade.entry_observation_id,
                "exit_observation_id": trade.exit_observation_id,
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "rsi": Decimal(str(entry.rsi)) if entry and entry.rsi is not None else None,
                "r0_rule": "RSI < 35",
                "variant_rule": (
                    "RSI disponible; filtre de valeur neutralisé"
                    if variant.diagnostic_control
                    else f"RSI {variant.operator} {variant.threshold}"
                ),
                "pnl": trade.realized_pnl,
                "return_ratio": trade.return_ratio,
                "duration_bars": trade.duration_bars,
                "exit_reason": str(getattr(trade.exit_reason, "value", trade.exit_reason)),
                "fees": trade.entry_fee + trade.exit_fee,
            }
        )
    return {
        "common_count": len(common),
        "additional_count": len(added),
        "disappeared_count": len(removed),
        "additional_trades": provenance,
        "disappeared_trade_keys": [list(item) for item in removed],
        "sequence_note": (
            "clés exactes entrée/sortie/raison; les différences incluent les effets "
            "de séquence et de position unique"
        ),
    }


def _outcome_comparison(
    outcomes: Sequence[ForwardOutcome],
    *,
    baseline: Sequence[SignalObservation],
    candidate: Sequence[SignalObservation],
) -> dict[str, Any]:
    baseline_ids = {item.id for item in baseline if item.accepted}
    candidate_ids = {item.id for item in candidate if item.accepted}
    newly_accepted = candidate_ids - baseline_ids
    by_horizon: dict[str, Any] = {}
    for horizon in sorted({item.horizon for item in outcomes}):
        selected = [
            item
            for item in outcomes
            if item.horizon == horizon
            and item.observation_id in newly_accepted
            and item.valid
            and not item.censored
            and item.net_return is not None
        ]
        returns = [Decimal(str(item.net_return)) for item in selected]
        by_horizon[str(horizon)] = {
            **_distribution(returns),
            "mean": (sum(returns, Decimal("0")) / Decimal(len(returns)) if returns else None),
            "positive_ratio": (
                Decimal(sum(value > 0 for value in returns)) / Decimal(len(returns))
                if returns
                else None
            ),
            "mfe": _distribution(
                Decimal(str(item.mfe)) for item in selected if item.mfe is not None
            ),
            "mae": _distribution(
                Decimal(str(item.mae)) for item in selected if item.mae is not None
            ),
        }
    return {
        "newly_accepted_observation_count": len(newly_accepted),
        "by_horizon": by_horizon,
        "note": "outcomes indépendants; jamais sommés ni utilisés comme P&L",
    }


def _dataset_stage(
    prepared: PreparedDataset,
    *,
    segment_name: str,
    variant_ids: Sequence[str],
) -> dict[str, Any]:
    timestamps = [item.source_open_time for item in prepared.steps]
    segments = {item.name: item for item in chronological_segments(timestamps)}
    segment = segments[segment_name]
    original = prepared.observations[segment.start_index : segment.end_index]
    original_ids = {item.id for item in original}
    segment_outcomes = tuple(
        item for item in prepared.outcomes if item.observation_id in original_ids
    )
    base_steps = prepared.steps[segment.start_index : segment.end_index]
    variant_observations = {
        name: tuple(apply_variant(item, VARIANTS[name]) for item in original)
        for name in variant_ids
    }
    if all(name in variant_observations for name in VARIANT_ORDER):
        assert_variant_invariants(original, variant_observations)
    elif "R0" in variant_observations:
        assert_variant_invariants(original, {"R0": variant_observations["R0"]})
    simulations = {
        name: simulate_portfolio(
            symbol=prepared.selection.symbol,
            steps=_variant_steps(base_steps, observations),
            config=prepared.portfolio_config,
        )
        for name, observations in variant_observations.items()
    }
    baseline = simulations["R0"]
    results: dict[str, Any] = {}
    for name in variant_ids:
        observations = variant_observations[name]
        simulation = simulations[name]
        metrics = _extended_metrics(simulation)
        concentration = profit_concentration(simulation.trades)
        rsi_groups = {
            "all": _distribution(
                Decimal(str(item.rsi)) for item in observations if item.rsi is not None
            ),
            "rejected_by_rsi": _distribution(
                Decimal(str(item.rsi))
                for item in observations
                if item.rsi is not None and not rsi_filter_passes(item, VARIANTS[name])
            ),
            "accepted": _distribution(
                Decimal(str(item.rsi))
                for item in observations
                if item.rsi is not None and item.accepted
            ),
            "entries": _distribution(
                Decimal(str(item.rsi))
                for item in observations
                if item.rsi is not None
                and str(item.id) in {trade.entry_observation_id for trade in simulation.trades}
            ),
            "winning_entries": _distribution(
                Decimal(str(item.rsi))
                for item in observations
                if item.rsi is not None
                and str(item.id)
                in {
                    trade.entry_observation_id
                    for trade in simulation.trades
                    if trade.realized_pnl > 0
                }
            ),
            "losing_entries": _distribution(
                Decimal(str(item.rsi))
                for item in observations
                if item.rsi is not None
                and str(item.id)
                in {
                    trade.entry_observation_id
                    for trade in simulation.trades
                    if trade.realized_pnl < 0
                }
            ),
        }
        comparison = _trade_comparison(baseline, simulation, observations, VARIANTS[name])
        additional_entry_ids = {
            item["entry_observation_id"] for item in comparison["additional_trades"]
        }
        results[name] = {
            "funnel": _funnel(observations, VARIANTS[name]),
            "orders": order_diagnostics(simulation),
            "metrics": metrics,
            "profit_concentration": concentration,
            "rsi_distribution": rsi_groups,
            "trade_duration": {
                "all": _distribution(Decimal(trade.duration_bars) for trade in simulation.trades),
                "additional": _distribution(
                    Decimal(trade.duration_bars)
                    for trade in simulation.trades
                    if trade.entry_observation_id in additional_entry_ids
                ),
                "by_exit_reason": {
                    reason: _distribution(
                        Decimal(trade.duration_bars)
                        for trade in simulation.trades
                        if str(getattr(trade.exit_reason, "value", trade.exit_reason)) == reason
                    )
                    for reason in sorted(
                        {
                            str(getattr(trade.exit_reason, "value", trade.exit_reason))
                            for trade in simulation.trades
                        }
                    )
                },
            },
            "accepted_without_distinct_entry": max(
                0,
                sum(item.accepted for item in observations)
                - len({trade.entry_observation_id for trade in simulation.trades}),
            ),
            "trade_comparison": comparison,
            "newly_accepted_outcomes": _outcome_comparison(
                segment_outcomes,
                baseline=variant_observations["R0"],
                candidate=observations,
            ),
            "_simulation": simulation,
        }
    return {
        "dataset": {
            "symbol": prepared.selection.symbol,
            "timeframe": prepared.selection.timeframe,
            "start": segment.start,
            "end": segment.end,
            "observations": segment.end_index - segment.start_index,
        },
        "variants": results,
    }


def _aggregate_variant(dataset_results: Sequence[dict[str, Any]], variant: str) -> dict[str, Any]:
    items = [item["variants"][variant] for item in dataset_results]
    funnels: Counter[str] = Counter()
    first_rejections: Counter[str] = Counter()
    overlaps: Counter[str] = Counter()
    for item in items:
        for name, value in item["funnel"].items():
            if isinstance(value, int):
                funnels[name] += value
        first_rejections.update(item["funnel"]["first_rejection_stages"])
        overlaps.update(item["funnel"]["rejection_overlaps"])
    metrics = [item["metrics"] for item in items]
    gross_profit = sum((Decimal(item["gross_profit"]) for item in metrics), Decimal("0"))
    gross_loss = sum((Decimal(item["gross_loss"]) for item in metrics), Decimal("0"))
    total_trades = sum(int(item["trade_count"]) for item in metrics)
    total_initial = sum((Decimal(item["initial_capital"]) for item in metrics), Decimal("0"))
    net_profit = sum((Decimal(item["net_profit"]) for item in metrics), Decimal("0"))
    winning = sum(int(item["winning_trade_count"]) for item in metrics)
    fees = sum((Decimal(item["total_fees"]) for item in metrics), Decimal("0"))
    additional_by_dataset = {
        f"{dataset['dataset']['symbol']}|{dataset['dataset']['timeframe']}": int(
            dataset["variants"][variant]["trade_comparison"]["additional_count"]
        )
        for dataset in dataset_results
        if dataset["variants"][variant]["trade_comparison"]["additional_count"]
    }
    all_trades = [
        trade
        for item in items
        for trade in cast(PortfolioSimulationResult, item["_simulation"]).trades
    ]
    concentration = profit_concentration(all_trades)
    return {
        "funnel": {
            **dict(funnels),
            "first_rejection_stages": dict(first_rejections),
            "rejection_overlaps": dict(overlaps),
        },
        "metrics": {
            "trade_count": total_trades,
            "net_profit_sum_non_combinable_accounts": net_profit,
            "net_return_equal_weight_accounts": (
                net_profit / total_initial if total_initial else None
            ),
            "max_drawdown_ratio": max(
                (Decimal(item["max_drawdown_ratio"]) for item in metrics),
                default=Decimal("0"),
            ),
            "profit_factor": gross_profit / abs(gross_loss) if gross_loss else None,
            "win_rate": Decimal(winning) / Decimal(total_trades) if total_trades else None,
            "average_trade_return": (
                sum(
                    (
                        Decimal(item["average_trade_return"]) * int(item["trade_count"])
                        for item in metrics
                        if item["average_trade_return"] is not None
                    ),
                    Decimal("0"),
                )
                / Decimal(total_trades)
                if total_trades
                else None
            ),
            "total_fees": fees,
            "exposure_ratio_weighted": (
                sum(
                    Decimal(item["exposure_ratio"])
                    * int(dataset_results[index]["dataset"]["observations"])
                    for index, item in enumerate(metrics)
                )
                / Decimal(sum(item["dataset"]["observations"] for item in dataset_results))
            ),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "top_5_profit_concentration": concentration["best_5"]["share_of_total"],
            "markets_with_trades": sum(int(item["trade_count"]) > 0 for item in metrics),
        },
        "additional_trade_datasets": additional_by_dataset,
    }


def _strip_internal(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_internal(value) for key, value in payload.items() if not key.startswith("_")
        }
    if isinstance(payload, list):
        return [_strip_internal(item) for item in payload]
    return payload


def evaluate_stage(
    prepared: Sequence[PreparedDataset],
    *,
    stage: str,
    variant_ids: Sequence[str],
    manifest_digest: str,
) -> dict[str, Any]:
    segment = STAGE_SEGMENTS[stage]
    dataset_results = [
        _dataset_stage(item, segment_name=segment, variant_ids=variant_ids) for item in prepared
    ]
    aggregates = {name: _aggregate_variant(dataset_results, name) for name in variant_ids}
    return _strip_internal(
        {
            "version": VERSION,
            "stage": stage,
            "manifest_hash": manifest_digest,
            "baseline_fingerprint": BASELINE_FINGERPRINT,
            "variants_executed": list(variant_ids),
            "datasets": dataset_results,
            "aggregate": aggregates,
        }
    )


def development_survivors(payload: Mapping[str, Any]) -> dict[str, list[str]]:
    baseline = payload["aggregate"]["R0"]
    baseline_trades = int(baseline["metrics"]["trade_count"])
    baseline_accepted = int(baseline["funnel"]["accepted"])
    baseline_drawdown = Decimal(baseline["metrics"]["max_drawdown_ratio"])
    baseline_profit_factor = baseline["metrics"]["profit_factor"]
    minimum_trades = max(30, 2 * baseline_trades)
    decisions: dict[str, list[str]] = {"R0": []}
    for name in ("R1", "R2", "R3"):
        item = payload["aggregate"][name]
        metrics = item["metrics"]
        funnel = item["funnel"]
        reasons: list[str] = []
        trade_count = int(metrics["trade_count"])
        if trade_count < minimum_trades:
            reasons.append(f"trades<{minimum_trades}")
        if int(funnel["accepted"]) <= baseline_accepted:
            reasons.append("accepted_not_increased")
        if Decimal(metrics["max_drawdown_ratio"]) > baseline_drawdown * Decimal("2"):
            reasons.append("drawdown_above_2x_baseline")
        gross_profit = Decimal(metrics["gross_profit"])
        fees = Decimal(metrics["total_fees"])
        if gross_profit > 0 and fees / gross_profit > Decimal("0.75"):
            reasons.append("costs_above_75pct_gross_profit")
        concentration = metrics["top_5_profit_concentration"]
        net_profit = Decimal(metrics["net_profit_sum_non_combinable_accounts"])
        if (
            concentration is not None
            and net_profit > 0
            and Decimal(concentration) > Decimal("0.80")
        ):
            reasons.append("top5_concentration_above_80pct")
        if len(item["additional_trade_datasets"]) < 2:
            reasons.append("new_trades_on_fewer_than_2_datasets")
        candidate_pf = metrics["profit_factor"]
        if (
            baseline_profit_factor is not None
            and candidate_pf is not None
            and Decimal(candidate_pf) < Decimal(baseline_profit_factor)
            and trade_count < 3 * max(1, baseline_trades)
        ):
            reasons.append("profit_factor_lower_without_3x_sample")
        decisions[name] = reasons
    return decisions


def validation_selection(
    payload: Mapping[str, Any],
    development: Mapping[str, Any],
) -> tuple[str | None, dict[str, list[str]]]:
    baseline = payload["aggregate"]["R0"]
    baseline_metrics = baseline["metrics"]
    baseline_trades = int(baseline_metrics["trade_count"])
    baseline_return = Decimal(baseline_metrics["net_return_equal_weight_accounts"])
    baseline_drawdown = Decimal(baseline_metrics["max_drawdown_ratio"])
    baseline_pf = baseline_metrics["profit_factor"]
    drawdown_cap = max(
        baseline_drawdown + Decimal("0.02"),
        baseline_drawdown * Decimal("1.5"),
    )
    decisions: dict[str, list[str]] = {"R0": []}
    contenders: list[str] = []
    for name in payload["variants_executed"]:
        if name == "R0":
            continue
        item = payload["aggregate"][name]
        metrics = item["metrics"]
        reasons: list[str] = []
        if int(metrics["trade_count"]) < max(10, baseline_trades):
            reasons.append("validation_trade_count_insufficient")
        candidate_return = Decimal(metrics["net_return_equal_weight_accounts"])
        if candidate_return < baseline_return:
            reasons.append("validation_return_below_baseline")
        if Decimal(metrics["max_drawdown_ratio"]) > drawdown_cap:
            reasons.append("validation_drawdown_above_cap")
        candidate_pf = metrics["profit_factor"]
        if baseline_pf is not None:
            if candidate_pf is None or Decimal(candidate_pf) < Decimal(baseline_pf):
                reasons.append("validation_profit_factor_below_baseline")
        elif int(baseline_metrics["trade_count"]) == 0:
            if candidate_return < 0:
                reasons.append("validation_negative_return_against_zero_trade_baseline")
            if candidate_pf is not None and Decimal(candidate_pf) < Decimal("1"):
                reasons.append("validation_profit_factor_below_1")
        if len(item["additional_trade_datasets"]) < 2:
            reasons.append("validation_new_trades_on_fewer_than_2_datasets")
        decisions[name] = reasons
        if not reasons:
            contenders.append(name)
    priority = {"R1": 1, "R2": 2, "R3": 3}
    contenders.sort(
        key=lambda name: (
            -int(payload["aggregate"][name]["metrics"]["trade_count"]),
            -Decimal(payload["aggregate"][name]["metrics"]["net_return_equal_weight_accounts"]),
            Decimal(payload["aggregate"][name]["metrics"]["max_drawdown_ratio"]),
            priority[name],
        )
    )
    return (contenders[0] if contenders else None), decisions


def conclusion_without_final(
    development: Mapping[str, Any],
    selected: str | None,
) -> str:
    if selected is not None:
        return "promising_but_insufficient"
    decisions = development.get("survival_decisions", {})
    if decisions and all(decisions.get(name) for name in ("R1", "R2", "R3")):
        return "no_variant_increased_sample_enough"
    return "rejected_on_validation"


def guard_final_test(
    *,
    manifest_path: Path,
    manifest_digest: str,
    selected_variants: Sequence[str],
    selection: Mapping[str, Any] | None,
    validation: Mapping[str, Any] | None,
) -> str:
    """Refuse toute ouverture prématurée ou sélection ambiguë."""
    load_manifest(manifest_path)
    if manifest_hash(manifest_path) != manifest_digest:
        raise ExperimentInvalidated("hash du manifeste modifié")
    if len(selected_variants) != 1:
        raise ExperimentInvalidated("le test final exige exactement une variante")
    selected = selected_variants[0]
    if selected not in {"R1", "R2", "R3"}:
        raise ExperimentInvalidated("variante finale non préenregistrée")
    if validation is None or validation.get("stage") != "validation":
        raise ExperimentInvalidated("résultats de validation absents")
    if selection is None:
        raise ExperimentInvalidated("fichier de sélection absent")
    if selection.get("manifest_hash") != manifest_digest:
        raise ExperimentInvalidated("sélection liée à un autre manifeste")
    if selection.get("baseline_fingerprint") != BASELINE_FINGERPRINT:
        raise ExperimentInvalidated("sélection liée à une autre baseline")
    if selection.get("selected_variant") != selected:
        raise ExperimentInvalidated("identifiant différent de la sélection gelée")
    if selected not in validation.get("variants_executed", []):
        raise ExperimentInvalidated("candidate non exécutée en validation")
    if validation.get("selected_variant") != selected:
        raise ExperimentInvalidated("candidate non issue de la validation")
    if validation.get("manifest_hash") != manifest_digest:
        raise ExperimentInvalidated("validation liée à un autre manifeste")
    return selected


def final_conclusion(payload: Mapping[str, Any], selected: str) -> str:
    baseline = payload["aggregate"]["R0"]["metrics"]
    candidate = payload["aggregate"][selected]["metrics"]
    baseline_return = Decimal(baseline["net_return_equal_weight_accounts"])
    candidate_return = Decimal(candidate["net_return_equal_weight_accounts"])
    baseline_drawdown = Decimal(baseline["max_drawdown_ratio"])
    drawdown_cap = max(
        baseline_drawdown + Decimal("0.02"),
        baseline_drawdown * Decimal("1.5"),
    )
    if int(candidate["trade_count"]) < 15:
        return "promising_but_insufficient"
    if (
        int(candidate["trade_count"]) > int(baseline["trade_count"])
        and candidate_return > baseline_return
        and candidate_return >= 0
        and Decimal(candidate["max_drawdown_ratio"]) <= drawdown_cap
    ):
        return "confirmed_for_production_candidate"
    return "rejected_on_final_test"


def _canonical_config(selection: DatasetSelection) -> BacktestConfig:
    return BacktestConfig(
        symbols=[selection.symbol],
        start=selection.start,
        end=selection.end,
        signal_config=ScanConfig(
            timeframe=cast(Timeframe, selection.timeframe),
            quote="USDC",
        ),
        horizons=[1, 3, 6, 12, 24],
        replay_mode="every_bar",
        entry_policy="next_open",
        gap_policy="reject_range",
        fee_bps=10,
        slippage_bps=0,
        snapshot_status="confirmed",
        portfolio_simulation=PortfolioSimulationConfigV1.model_validate(
            {
                "version": 1,
                "quote_asset": selection.symbol.rsplit("/", 1)[-1],
                "initial_capital": "10000",
                "position_sizing": {"mode": "percent_cash", "value": "100"},
                "execution_policy": "next_open",
                "fee_rate": "0.001",
                "slippage_rate": "0",
                "end_of_test_policy": "force_close",
            }
        ),
    )


def _validate_selection_against_manifest(
    selections: Sequence[DatasetSelection], manifest: Mapping[str, Any]
) -> None:
    actual = [
        {
            "symbol": item.symbol,
            "timeframe": item.timeframe,
            "start": item.start.isoformat().replace("+00:00", "Z"),
            "end": item.end.isoformat().replace("+00:00", "Z"),
            "candles": item.candle_count,
        }
        for item in selections
    ]
    expected = [
        {key: item[key] for key in ("symbol", "timeframe", "start", "end", "candles")}
        for item in manifest["datasets"]
    ]
    if actual != expected:
        raise ExperimentInvalidated("datasets différents du manifeste baseline")


async def prepare_full(
    *,
    database_path: Path,
    manifest: Mapping[str, Any],
    generated_at: datetime,
) -> tuple[PreparedDataset, ...]:
    inventory = inventory_datasets(database_path)
    selections = select_datasets(database_path, inventory, mode="full")
    _validate_selection_against_manifest(selections, manifest)
    source = ReadOnlyHistoricalRepository(database_path)
    prepared: list[PreparedDataset] = []
    with tempfile.TemporaryDirectory(prefix="rsi-filter-v1-") as temporary:
        database = Database(Path(temporary) / "results.sqlite3")
        await database.initialize()
        repositories = BacktestRepository(database)
        portfolios = PortfolioRepository(database)
        for selection in selections:
            config = _canonical_config(selection)
            job = BacktestJob(
                id=(
                    "rsi-v1-"
                    + stable_fingerprint(
                        {"dataset": asdict(selection), "config": config.model_dump(mode="json")}
                    ).split(":", 1)[1][:16]
                ),
                status=BacktestStatus.RUNNING,
                config=config,
                created_at=generated_at,
                started_at=generated_at,
            )
            await repositories.save_job(job)
            engine = BacktestEngine(source, repositories, portfolios=portfolios, yield_every=250)
            await engine.run(job)
            observations = tuple(await repositories.all_observations(job.id))
            outcomes = tuple(await repositories.all_outcomes(job.id))
            portfolio = await portfolios.load_portfolio_simulation_result(job.id)
            if portfolio is None:
                raise ExperimentInvalidated(f"portefeuille absent: {selection.key}")
            candles = source.selected_candles(selection)
            steps = build_portfolio_simulation_steps(
                symbol=selection.symbol,
                timeframe=selection.timeframe,
                observations=observations,
                primary_candles=candles,
            )
            prepared.append(
                PreparedDataset(
                    selection=selection,
                    observations=observations,
                    outcomes=outcomes,
                    steps=steps,
                    portfolio_config=portfolio.config,
                )
            )
            await repositories.delete_job(job.id)
        await database.close()
    return tuple(prepared)


def prepare_quick() -> tuple[PreparedDataset, ...]:
    """Jeu synthétique déterministe, sans SQLite historique ni réseau."""
    prepared: list[PreparedDataset] = []
    patterns = (
        ("BTC/USDC", "4h", 4),
        ("LINK/USDC", "1h", 1),
    )
    for dataset_index, (symbol, timeframe, hours) in enumerate(patterns):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=dataset_index)
        observations: list[SignalObservation] = []
        steps: list[PortfolioSimulationStep] = []
        for index in range(120):
            opened = start + timedelta(hours=index * hours)
            decision = opened + timedelta(hours=hours)
            # Les quatre zones créent des séquences distinctes et monotones.
            rsi = (30.0, 37.0, 42.0, 52.0)[(index // 3) % 4]
            other_pass = index % 29 != 0
            rsi_pass = rsi < 35
            accepted = rsi_pass and other_pass
            observation_id = dataset_index * 10_000 + index + 1
            observations.append(
                SignalObservation(
                    id=observation_id,
                    job_id=f"quick-{dataset_index}",
                    symbol=symbol,
                    timeframe=timeframe,
                    decision_time=decision,
                    created_at=decision,
                    source_open_time=opened,
                    accepted=accepted,
                    rejection_stage=(None if accepted else "rsi" if not rsi_pass else "trend"),
                    rejection_reason=(
                        None
                        if accepted
                        else "rsi_indisponible_ou_seuil" if not rsi_pass else "tendance_sous_seuil"
                    ),
                    close=100 + index * 0.1,
                    rsi=rsi,
                    trend_score=2 if other_pass else 1,
                    availability={
                        "rsi": "available",
                        "trend": "available",
                        "macd": "available",
                        "bollinger": "available",
                        "stochastic": "available",
                    },
                    filter_trace=[
                        {
                            "stage": "rsi",
                            "passed": rsi_pass,
                            "reason": None if rsi_pass else "rsi_indisponible_ou_seuil",
                        },
                        {
                            "stage": "trend",
                            "passed": other_pass,
                            "reason": None if other_pass else "tendance_sous_seuil",
                        },
                        {"stage": "signal_filters", "passed": True, "reason": None},
                        {"stage": "confluence", "passed": True, "reason": None},
                    ],
                )
            )
            wave = Decimal((index % 12) - 5) / Decimal("10")
            steps.append(
                PortfolioSimulationStep(
                    observation_id=str(observation_id),
                    source_open_time=opened,
                    decision_time=decision,
                    open_price=Decimal("100") + Decimal(index) / Decimal("20") + wave,
                    close_price=Decimal("100.1") + Decimal(index) / Decimal("20") + wave,
                    accepted=accepted,
                )
            )
        selection = DatasetSelection(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=start + timedelta(hours=120 * hours),
            candle_count=120,
            continuity_ratio=Decimal("1"),
            reason="fixture synthétique quick pré-définie",
        )
        prepared.append(
            PreparedDataset(
                selection=selection,
                observations=tuple(observations),
                outcomes=(),
                steps=tuple(steps),
                portfolio_config=PortfolioSimulationConfig(
                    quote_asset="USDC",
                    initial_capital=Decimal("10000"),
                    position_size_percent=Decimal("100"),
                    fee_rate=Decimal("0.001"),
                    slippage_rate=Decimal("0"),
                ),
            )
        )
    return tuple(prepared)


def write_cache(
    path: Path,
    *,
    prepared: Sequence[PreparedDataset],
    manifest_digest: str,
    mode: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": VERSION,
        "manifest_hash": manifest_digest,
        "mode": mode,
        "prepared": tuple(prepared),
    }
    with gzip.open(path, "wb", compresslevel=5) as stream:
        pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)


def read_cache(path: Path, *, manifest_digest: str, mode: str) -> tuple[PreparedDataset, ...]:
    if not path.is_file():
        raise ExperimentInvalidated("cache canonique absent; exécuter reproduce")
    with gzip.open(path, "rb") as stream:
        payload = pickle.load(stream)  # noqa: S301 - cache local produit par ce module
    if (
        payload.get("version") != VERSION
        or payload.get("manifest_hash") != manifest_digest
        or payload.get("mode") != mode
    ):
        raise ExperimentInvalidated("cache canonique incompatible")
    return cast(tuple[PreparedDataset, ...], payload["prepared"])


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _jsonable(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _overall_reproduction(prepared: Sequence[PreparedDataset]) -> dict[str, Any]:
    accepted = transitions_up = transitions_down = orders = executed = rejected = trades = 0
    datasets = []
    for item in prepared:
        variants = tuple(
            apply_variant(observation, VARIANTS["R0"]) for observation in item.observations
        )
        assert_variant_invariants(item.observations, {"R0": variants})
        up, down = _transitions(variants)
        simulation = simulate_portfolio(
            symbol=item.selection.symbol,
            steps=_variant_steps(item.steps, variants),
            config=item.portfolio_config,
        )
        order_counts = order_diagnostics(simulation)
        accepted += sum(observation.accepted for observation in variants)
        transitions_up += up
        transitions_down += down
        orders += order_counts["order_count"]
        executed += order_counts["executed_count"]
        rejected += order_counts["rejected_count"]
        trades += len(simulation.trades)
        datasets.append(
            {
                "symbol": item.selection.symbol,
                "timeframe": item.selection.timeframe,
                "candles": len(variants),
                "accepted": sum(observation.accepted for observation in variants),
                "trades": len(simulation.trades),
                "metrics": _extended_metrics(simulation),
            }
        )
    counts = {
        "candles": sum(len(item.observations) for item in prepared),
        "observations": sum(len(item.observations) for item in prepared),
        "accepted": accepted,
        "false_to_true": transitions_up,
        "true_to_false": transitions_down,
        "orders": orders,
        "executed_orders": executed,
        "rejected_orders": rejected,
        "trades": trades,
    }
    return {"counts": counts, "datasets": datasets}


def reproduce(prepared: Sequence[PreparedDataset], *, mode: str) -> dict[str, Any]:
    result = _overall_reproduction(prepared)
    if mode == "full" and result["counts"] != BASELINE_COUNTS:
        raise ExperimentInvalidated(
            f"baseline non reproduite: attendu {BASELINE_COUNTS}, obtenu {result['counts']}"
        )
    return result


def _stage_path(output: Path, stage: str) -> Path:
    suffix = {
        "reproduce": "reproduction",
        "development": "development",
        "validation": "validation",
        "final-test": "final",
    }[stage]
    return output / f"rsi-filter-experiment-v1-{suffix}.json"


def _selection_payload(
    *,
    manifest_digest: str,
    selected: str,
    development: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "version": VERSION,
        "manifest_hash": manifest_digest,
        "baseline_fingerprint": BASELINE_FINGERPRINT,
        "selected_variant": selected,
        "selection_reason": (
            "garde-fous satisfaits; maximum trades validation, puis rendement, "
            "drawdown et relaxation minimale"
        ),
        "development_metrics": development["aggregate"][selected]["metrics"],
        "validation_metrics": validation["aggregate"][selected]["metrics"],
        "selected_at": max(dataset["dataset"]["end"] for dataset in validation["datasets"]),
    }


def _sensitivity(
    prepared: Sequence[PreparedDataset],
    *,
    selected: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {"fees": {}, "slippage": {}}
    for family, values in (
        ("fees", ("0", "0.0005", "0.001", "0.002")),
        ("slippage", ("0", "0.0005", "0.001", "0.002")),
    ):
        for value in values:
            scenario: dict[str, Any] = {}
            for variant_name in ("R0", selected):
                metrics = []
                for item in prepared:
                    observations = tuple(
                        apply_variant(observation, VARIANTS[variant_name])
                        for observation in item.observations
                    )
                    config = (
                        replace(item.portfolio_config, fee_rate=Decimal(value))
                        if family == "fees"
                        else replace(item.portfolio_config, slippage_rate=Decimal(value))
                    )
                    simulation = simulate_portfolio(
                        symbol=item.selection.symbol,
                        steps=_variant_steps(item.steps, observations),
                        config=config,
                    )
                    metrics.append(_extended_metrics(simulation))
                net = sum((Decimal(item["net_profit"]) for item in metrics), Decimal("0"))
                initial = sum((Decimal(item["initial_capital"]) for item in metrics), Decimal("0"))
                scenario[variant_name] = {
                    "trade_count": sum(int(item["trade_count"]) for item in metrics),
                    "net_return_equal_weight_accounts": net / initial,
                    "max_drawdown_ratio": max(
                        Decimal(item["max_drawdown_ratio"]) for item in metrics
                    ),
                    "profit_factor": (
                        sum(
                            (Decimal(item["gross_profit"]) for item in metrics),
                            Decimal("0"),
                        )
                        / abs(
                            sum(
                                (Decimal(item["gross_loss"]) for item in metrics),
                                Decimal("0"),
                            )
                        )
                        if any(Decimal(item["gross_loss"]) for item in metrics)
                        else None
                    ),
                    "total_fees": sum(
                        (Decimal(item["total_fees"]) for item in metrics), Decimal("0")
                    ),
                }
            result[family][value] = scenario
    return result


def render_results_report(
    *,
    output: Path,
    manifest_digest: str,
) -> Path:
    reproduction = read_json(_stage_path(output, "reproduce"))
    development = read_json(_stage_path(output, "development"))
    validation = read_json(_stage_path(output, "validation"))
    final = read_json(_stage_path(output, "final-test"))
    if development is None:
        conclusion = "experiment_invalidated"
    elif final is not None:
        conclusion = str(final.get("conclusion", "experiment_invalidated"))
    elif validation is not None:
        conclusion = str(validation.get("conclusion", "experiment_invalidated"))
    else:
        conclusion = "experiment_invalidated"

    def table(stage: Mapping[str, Any] | None) -> str:
        if stage is None:
            return "_Stage non exécuté._"
        rows = [
            "| Variante | Observations | Accepted | Rejets RSI | Trades | Rendement | Drawdown | PF |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for name in stage["variants_executed"]:
            item = stage["aggregate"][name]
            rows.append(
                f"| {name} | {item['funnel']['observations']} | "
                f"{item['funnel']['accepted']} | {item['funnel']['rsi_fail']} | "
                f"{item['metrics']['trade_count']} | "
                f"{item['metrics']['net_return_equal_weight_accounts']} | "
                f"{item['metrics']['max_drawdown_ratio']} | "
                f"{item['metrics']['profit_factor']} |"
            )
        return "\n".join(rows)

    selection = read_json(output / "rsi-filter-experiment-v1-selection.json")
    reproduction_json = json.dumps(
        reproduction or {"status": "absente"}, ensure_ascii=False, indent=2
    )
    survival_json = json.dumps(
        (development or {}).get("survival_decisions", {}),
        ensure_ascii=False,
        indent=2,
    )
    selection_json = json.dumps(
        selection or {"selected_variant": None}, ensure_ascii=False, indent=2
    )
    report = f"""# Résultats — expérience filtre RSI v1

## 1. Résumé exécutif

Conclusion catégorisée : `{conclusion}`. La production reste inchangée. Le
filtre réel est `RSI < 35`; sa période est 14 et son calcul Wilder/EWM n'a pas
été modifié.

## 2. Hypothèse, règle et variantes

R0 `<35`, R1 `<40`, R2 `<45`, R3 contrôle sans prédicat de valeur. Les quatre
variantes exigent une valeur RSI finie avec statut `available`. Les opérateurs
stricts, la direction, le signal structuré et tous les autres filtres sont
inchangés.

## 3. Manifeste, datasets et segments

- hash préenregistré : `{manifest_digest}`
- fingerprint baseline : `{BASELINE_FINGERPRINT}`
- cinq plages Phase 7.1, segmentation chronologique 60/20/20 inchangée
- capital 10 000, sizing 100 %, frais 0,001, slippage 0, `next_open`,
  `force_close`

## 4. Baseline reproduite

```json
{reproduction_json}
```

## 5. Développement — funnel, transitions, ordres et trades

{table(development)}

Décisions de survie :
```json
{survival_json}
```

## 6. Validation, sélection et test final

{table(validation)}

Sélection gelée :
```json
{selection_json}
```

Test final :

{table(final)}

## 7. Rejets RSI seuls, chevauchements et nouveau goulot

Les champs `rsi_only_rejections`, `rejection_overlaps` et
`first_rejection_stages` de chaque funnel distinguent le rejet contrefactuel du
premier rejet observé. Après relaxation, le nouveau goulot est la valeur
non-RSI la plus fréquente de `first_rejection_stages`.

## 8. Provenance, séquences et coûts

Chaque dataset contient les comptes de trades communs, supplémentaires et
disparus. Les nouveaux trades sont reliés par IDs exacts d'observation,
entrée/sortie/raison, avec RSI, P&L, rendement, durée et frais. Les séquences
accepted et transitions montrent les prolongements ou fusions dus à la
stratégie à position unique. Les sensibilités frais/slippage n'existent que
dans le résultat final après sélection.

## 9. Distributions et outcomes

Les distributions RSI fournissent count/min/q10/q25/médiane/q75/q90/max pour
toutes les observations, rejets RSI, accepted et entrées. Aucun nouveau seuil
n'en est dérivé. Les outcomes restent indépendants du portefeuille et ne sont
jamais utilisés pour décider accepted.

## 10. Invariants et anti-look-ahead

- R0 identique au verdict canonique et à sa trace ;
- RSI, autres indicateurs, confluence, tendance et raw values identiques ;
- monotonie R0 → R1 → R2 et disponibilité conservée pour R3 ;
- aucune valeur future, outcome, trade ou segment suivant n'entre dans le verdict ;
- exécution et coûts identiques, aucune pyramide, clôture `end_of_test` conservée ;
- développement/validation n'exposent aucune métrique du test final.

## 11. Stabilité, limites et risque de surapprentissage

Les résultats sont ventilés par marché/timeframe dans les JSON de stage. Cinq
plages, presque toutes USDC, restent un échantillon faible. Aucun grid search,
nouveau marché, seuil a posteriori ou optimisation du test final n'a été
effectué. Une dépendance à un marché, une période ou quelques trades bloque la
promotion.

## 12. Conclusion et suite

Catégorie finale : `{conclusion}`.

Une Phase 7.3 n'est recommandée que si la catégorie est
`confirmed_for_production_candidate`. Dans tous les autres cas, la règle de
production `RSI < 35` est conservée et aucune relaxation de 15/20 points n'est
proposée a posteriori.
"""
    path = output / "rsi-filter-experiment-v1-results.md"
    path.write_text(report, encoding="utf-8", newline="\n")
    return path


def run_stage(
    *,
    stage: str,
    mode: str,
    database_path: Path,
    output: Path,
    manifest_path: Path,
    cache_path: Path,
    selected_variants: Sequence[str] = (),
) -> dict[str, Any]:
    started = time.perf_counter()
    manifest = load_manifest(manifest_path)
    digest = manifest_hash(manifest_path)
    reproduction_path = _stage_path(output, "reproduce")
    development_path = _stage_path(output, "development")
    validation_path = _stage_path(output, "validation")
    selection_path = output / "rsi-filter-experiment-v1-selection.json"

    if stage == "reproduce":
        prepared = (
            prepare_quick()
            if mode == "quick"
            else asyncio.run(
                prepare_full(
                    database_path=database_path,
                    manifest=manifest,
                    generated_at=datetime(2026, 7, 30, 10, tzinfo=timezone.utc),
                )
            )
        )
        write_cache(
            cache_path,
            prepared=prepared,
            manifest_digest=digest,
            mode=mode,
        )
        payload = {
            "version": VERSION,
            "stage": stage,
            "mode": mode,
            "manifest_hash": digest,
            "baseline_fingerprint": BASELINE_FINGERPRINT,
            **reproduce(prepared, mode=mode),
        }
    else:
        if read_json(reproduction_path) is None:
            raise ExperimentInvalidated("reproduction absente")
        prepared = read_cache(cache_path, manifest_digest=digest, mode=mode)
        if stage == "development":
            payload = evaluate_stage(
                prepared,
                stage=stage,
                variant_ids=VARIANT_ORDER,
                manifest_digest=digest,
            )
            payload["mode"] = mode
            payload["survival_decisions"] = development_survivors(payload)
            payload["survivors"] = [
                name for name in ("R1", "R2", "R3") if not payload["survival_decisions"][name]
            ]
        elif stage == "validation":
            development = read_json(development_path)
            if development is None:
                raise ExperimentInvalidated("développement absent")
            survivors = list(development.get("survivors", []))
            payload = evaluate_stage(
                prepared,
                stage=stage,
                variant_ids=("R0", *survivors),
                manifest_digest=digest,
            )
            payload["mode"] = mode
            selected, decisions = validation_selection(payload, development)
            payload["validation_decisions"] = decisions
            payload["selected_variant"] = selected
            payload["conclusion"] = conclusion_without_final(development, selected)
            if selected is not None:
                write_json(
                    selection_path,
                    _selection_payload(
                        manifest_digest=digest,
                        selected=selected,
                        development=development,
                        validation=payload,
                    ),
                )
            else:
                write_json(
                    _stage_path(output, "final-test"),
                    {
                        "version": VERSION,
                        "stage": "final-test",
                        "status": "not_opened",
                        "reason": "aucune variante survivante issue de la validation",
                        "manifest_hash": digest,
                        "baseline_fingerprint": BASELINE_FINGERPRINT,
                        "variants_executed": [],
                        "aggregate": {},
                        "selected_variant": None,
                        "conclusion": payload["conclusion"],
                    },
                )
        elif stage == "final-test":
            validation = read_json(validation_path)
            selection = read_json(selection_path)
            selected = guard_final_test(
                manifest_path=manifest_path,
                manifest_digest=digest,
                selected_variants=selected_variants,
                selection=selection,
                validation=validation,
            )
            payload = evaluate_stage(
                prepared,
                stage=stage,
                variant_ids=("R0", selected),
                manifest_digest=digest,
            )
            payload["mode"] = mode
            payload["selected_variant"] = selected
            payload["sensitivity"] = _sensitivity(prepared, selected=selected)
            payload["conclusion"] = final_conclusion(payload, selected)
        else:
            raise ExperimentInvalidated(f"stage inconnu: {stage}")
    payload["duration_seconds"] = Decimal(str(round(time.perf_counter() - started, 6)))
    write_json(_stage_path(output, stage), payload)
    render_results_report(output=output, manifest_digest=digest)
    return payload
