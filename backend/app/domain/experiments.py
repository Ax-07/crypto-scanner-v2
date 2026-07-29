"""Découpage temporel et évaluation explicable des candidats phase 4."""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections import Counter, defaultdict
from typing import Any, Sequence, cast

from app.models.backtest import ForwardOutcome, SignalObservation
from app.models.experiment import (
    CandidateResult,
    CandidateSpec,
    EvaluationWindow,
    ExperimentConfig,
)


def dataset_fingerprint(observations: Sequence[SignalObservation]) -> str:
    payload = "|".join(
        f"{item.id}:{item.symbol}:{item.timeframe}:{item.decision_time.isoformat()}"
        for item in observations
    )
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def chronological_split(
    observations: Sequence[SignalObservation], config: ExperimentConfig
) -> tuple[dict[str, list[SignalObservation]], list[EvaluationWindow]]:
    ordered = sorted(observations, key=lambda item: (item.decision_time, item.id or 0))
    if len(ordered) < config.split.embargo_bars * 2 + 3:
        raise ValueError("dataset trop court pour les splits et l'embargo demandés")
    train_end = int(len(ordered) * config.split.train_ratio)
    validation_end = train_end + int(len(ordered) * config.split.validation_ratio)
    embargo = config.split.embargo_bars
    indexes = {
        "train": (0, train_end - embargo),
        "validation": (train_end, validation_end - embargo),
        "test": (validation_end, len(ordered)),
    }
    groups: dict[str, list[SignalObservation]] = {}
    windows: list[EvaluationWindow] = []
    for name, (start, end) in indexes.items():
        group = ordered[start:end]
        if not group:
            raise ValueError(f"split {name} vide")
        groups[name] = group
        windows.append(
            EvaluationWindow(
                name=name,
                start=group[0].decision_time,
                end=group[-1].decision_time,
                observation_count=len(group),
            )
        )
    if not (windows[0].end < windows[1].start < windows[2].start):
        raise ValueError("chevauchement ou ordre chronologique invalide")
    return groups, windows


def walk_forward_folds(observations: Sequence[SignalObservation], config: ExperimentConfig) -> list[
    tuple[
        list[SignalObservation],
        list[SignalObservation],
        list[SignalObservation],
    ]
]:
    if not config.walk_forward.enabled:
        return []
    ordered = sorted(observations, key=lambda item: (item.decision_time, item.id or 0))
    wf, embargo = config.walk_forward, config.split.embargo_bars
    folds: list[
        tuple[list[SignalObservation], list[SignalObservation], list[SignalObservation]]
    ] = []
    cursor = wf.train_bars
    required = embargo + wf.validation_bars + embargo + wf.oos_bars
    while cursor + required <= len(ordered) and len(folds) < wf.max_folds:
        train = ordered[max(0, cursor - wf.train_bars) : cursor]
        validation = ordered[cursor + embargo : cursor + embargo + wf.validation_bars]
        oos_start = cursor + embargo + wf.validation_bars + embargo
        oos = ordered[oos_start : oos_start + wf.oos_bars]
        folds.append((train, validation, oos))
        cursor += wf.step_bars
    return folds


def _candidate_score(observation: SignalObservation, candidate: CandidateSpec) -> float | None:
    factors = {
        name: value
        for name, value in observation.confluence_factors.items()
        if value is not None and name not in candidate.excluded_factors
    }
    if candidate.trend_policy == "strict_consensus":
        states = [value for value in observation.trend_states.values() if value != "unavailable"]
        if states:
            factors["trend"] = (
                1.0
                if all(value == "bullish" for value in states)
                else (0.0 if all(value == "bearish" for value in states) else 0.5)
            )
    elif candidate.trend_policy in {"mtf_majority", "mtf_weighted"}:
        weights = {"1w": 3, "1d": 2, "4h": 1}
        votes = []
        for timeframe, state in observation.trend_states.items():
            if state == "unavailable":
                continue
            weight = weights.get(timeframe, 1) if candidate.trend_policy == "mtf_weighted" else 1
            votes.extend([{"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}[state]] * weight)
        if votes:
            factors["trend"] = statistics.fmean(votes)
    weights = candidate.weights or {name: 20 for name in factors}
    active = {name: weight for name, weight in weights.items() if name in factors and weight > 0}
    if not active:
        return None
    if candidate.group_scoring:
        mean_names = {"rsi", "bollinger", "stochastic"}
        trend_names = {"trend", "macd"}
        group_values = []
        for names in (mean_names, trend_names):
            available = [name for name in names if name in active]
            if available:
                total = sum(active[name] for name in available)
                score = sum(float(factors[name]) * active[name] for name in available) / total
                if names == mean_names and candidate.mean_reversion_cap is not None:
                    score = min(score, candidate.mean_reversion_cap / 100)
                group_values.append(score)
        return statistics.fmean(group_values) * 100 if group_values else None
    total = sum(active.values())
    return sum(float(factors[name]) * active[name] for name in active) / total * 100


def _accepted(item: SignalObservation, candidate: CandidateSpec) -> bool:
    if candidate.allowed_timeframes and item.timeframe not in candidate.allowed_timeframes:
        return False
    if (
        candidate.min_quote_volume is not None
        and float(item.quality.get("quote_volume_median", 0)) < candidate.min_quote_volume
    ):
        return False
    quality = 1.0 - max(
        float(item.quality.get("zero_volume_ratio", 0)),
        float(item.quality.get("constant_candle_ratio", 0)),
    )
    if quality < candidate.min_data_quality:
        return False
    if candidate.bollinger_policy == "below_mid" and item.bollinger_position not in {
        "below_mid",
        "below_lower",
    }:
        return False
    if candidate.bollinger_policy == "lower_band" and item.bollinger_position != "below_lower":
        return False
    if candidate.stochastic_policy == "bullish" and item.stochastic_signal != "bullish":
        return False
    if candidate.stochastic_policy == "oversold" and item.stochastic_signal != "oversold":
        return False
    if candidate.macd_policy == "bullish" and item.macd_signal != "bullish":
        return False
    if candidate.divergence_required:
        matching = [
            marker
            for marker in item.divergences
            if (not candidate.divergence_kinds or marker.get("kind") in candidate.divergence_kinds)
            and (
                not candidate.divergence_directions
                or marker.get("direction") in candidate.divergence_directions
            )
        ]
        if not matching:
            return False
    states = [state for state in item.trend_states.values() if state != "unavailable"]
    consensus = bool(states) and (
        all(state == "bullish" for state in states) or all(state == "bearish" for state in states)
    )
    if candidate.regime == "trend" and not consensus:
        return False
    if candidate.regime == "range" and consensus:
        return False
    if candidate.rsi_threshold is not None and (
        item.rsi is None or item.rsi >= candidate.rsi_threshold
    ):
        return False
    score = _candidate_score(item, candidate)
    threshold = candidate.min_confluence_score
    if threshold is not None and (score is None or score < threshold):
        return False
    return all(
        trace.get("passed", True)
        for trace in item.filter_trace
        if trace.get("stage") not in {"rsi", "confluence"}
    )


def _quantile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low, high = math.floor(position), math.ceil(position)
    return (
        ordered[low]
        if low == high
        else ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    )


def _block_bootstrap(
    values: list[float], *, samples: int = 500, block_size: int = 8, seed: int = 42
) -> dict[str, float | None]:
    if not values:
        return {"low": None, "high": None, "p_nonpositive": None}
    rng = random.Random(seed)
    size = len(values)
    block = min(block_size, size)
    means: list[float] = []
    for _ in range(samples):
        draw: list[float] = []
        while len(draw) < size:
            start = rng.randrange(size)
            draw.extend(values[(start + offset) % size] for offset in range(block))
        means.append(statistics.fmean(draw[:size]))
    return {
        "low": _quantile(means, 0.025),
        "high": _quantile(means, 0.975),
        "p_nonpositive": (sum(value <= 0 for value in means) + 1) / (samples + 1),
    }


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    count = len(p_values)
    adjusted = [1.0] * count
    running = 1.0
    for rank, index in reversed(
        list(enumerate(sorted(range(count), key=lambda item: p_values[item]), 1))
    ):
        running = min(running, p_values[index] * count / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def evaluate_metrics(
    observations: Sequence[SignalObservation],
    outcomes: Sequence[ForwardOutcome],
    candidate: CandidateSpec,
    horizon: int,
    bootstrap_samples: int = 500,
    bootstrap_block_size: int = 8,
) -> dict[str, Any]:
    accepted = {item.id: item for item in observations if _accepted(item, candidate)}
    selected = [
        outcome
        for outcome in outcomes
        if outcome.observation_id in accepted
        and outcome.horizon == horizon
        and not outcome.censored
        and outcome.net_return is not None
    ]
    net = [float(item.net_return) for item in selected if item.net_return is not None]
    gross = [float(item.gross_return) for item in selected if item.gross_return is not None]
    mfe = [float(item.mfe) for item in selected if item.mfe is not None]
    mae = [float(item.mae) for item in selected if item.mae is not None]
    by_symbol: dict[str, list[float]] = defaultdict(list)
    by_timeframe: dict[str, list[float]] = defaultdict(list)
    by_month: dict[str, list[float]] = defaultdict(list)
    by_year: dict[str, list[float]] = defaultdict(list)
    for outcome in selected:
        observation = accepted[outcome.observation_id]
        assert outcome.net_return is not None
        value = float(outcome.net_return)
        by_symbol[observation.symbol].append(value)
        by_timeframe[observation.timeframe].append(value)
        by_month[observation.decision_time.strftime("%Y-%m")].append(value)
        by_year[str(observation.decision_time.year)].append(value)
    count = len(net)
    symbol_counts = Counter(accepted[item.observation_id].symbol for item in selected)
    timeframe_counts = Counter(accepted[item.observation_id].timeframe for item in selected)
    bootstrap_seed = int(hashlib.sha256(f"{candidate.id}:{horizon}".encode()).hexdigest()[:8], 16)
    return {
        "observation_count": len(observations),
        "signal_count": count,
        "coverage": count / len(observations) if observations else 0,
        "gross_mean": statistics.fmean(gross) if gross else None,
        "gross_median": statistics.median(gross) if gross else None,
        "net_mean": statistics.fmean(net) if net else None,
        "net_median": statistics.median(net) if net else None,
        "positive_rate": sum(value > 0 for value in net) / count if count else None,
        "mfe_mean": statistics.fmean(mfe) if mfe else None,
        "mfe_median": statistics.median(mfe) if mfe else None,
        "mae_mean": statistics.fmean(mae) if mae else None,
        "mae_median": statistics.median(mae) if mae else None,
        "mfe_mae_ratio": (
            statistics.median(mfe) / abs(statistics.median(mae))
            if mfe and mae and statistics.median(mae)
            else None
        ),
        "dispersion": statistics.pstdev(net) if len(net) > 1 else None,
        "adverse_quantile_05": _quantile(net, 0.05) if net else None,
        "monthly_stability": _group_stability(by_month),
        "annual_stability": _group_stability(by_year),
        "symbol_stability": _group_stability(by_symbol),
        "timeframe_stability": _group_stability(by_timeframe),
        "symbol_count": len(by_symbol),
        "timeframe_count": len(by_timeframe),
        "minimum_timeframe_count": min(timeframe_counts.values(), default=0),
        "calendar_periods": len(by_month),
        "max_symbol_concentration": max(symbol_counts.values(), default=0) / count if count else 1,
        "friction_drag_mean": (
            statistics.fmean(gross) - statistics.fmean(net) if gross and net else None
        ),
        "bootstrap": _block_bootstrap(
            net,
            samples=bootstrap_samples,
            block_size=bootstrap_block_size,
            seed=bootstrap_seed,
        ),
    }


def _group_stability(groups: dict[str, list[float]]) -> dict[str, Any]:
    medians = {name: statistics.median(values) for name, values in groups.items() if values}
    return {
        "groups": len(medians),
        "positive_groups": sum(value > 0 for value in medians.values()),
        "median_of_medians": statistics.median(medians.values()) if medians else None,
        "range": max(medians.values()) - min(medians.values()) if len(medians) > 1 else 0,
        "values": medians,
    }


def evaluate_candidates(
    config: ExperimentConfig,
    observations: Sequence[SignalObservation],
    outcomes: Sequence[ForwardOutcome],
) -> tuple[list[CandidateResult], list[EvaluationWindow]]:
    splits, windows = chronological_split(observations, config)
    outcome_ids = {name: {item.id for item in group} for name, group in splits.items()}
    folds = walk_forward_folds(splits["train"] + splits["validation"], config)
    results: list[CandidateResult] = []
    for candidate in config.candidates:
        metrics = {
            name: evaluate_metrics(
                group,
                [item for item in outcomes if item.observation_id in outcome_ids[name]],
                candidate,
                config.selection_horizon,
                config.bootstrap_samples,
                config.bootstrap_block_size,
            )
            for name, group in splits.items()
        }
        fold_metrics = []
        fold_oos_groups: list[SignalObservation] = []
        for index, (train_group, validation_group, oos_group) in enumerate(folds):
            fold_oos_groups.extend(oos_group)
            train_ids = {item.id for item in train_group}
            validation_ids = {item.id for item in validation_group}
            oos_ids = {item.id for item in oos_group}
            fold_metrics.append(
                {
                    "fold": index + 1,
                    "train": evaluate_metrics(
                        train_group,
                        [item for item in outcomes if item.observation_id in train_ids],
                        candidate,
                        config.selection_horizon,
                        config.bootstrap_samples,
                        config.bootstrap_block_size,
                    ),
                    "validation": evaluate_metrics(
                        validation_group,
                        [item for item in outcomes if item.observation_id in validation_ids],
                        candidate,
                        config.selection_horizon,
                        config.bootstrap_samples,
                        config.bootstrap_block_size,
                    ),
                    "oos": evaluate_metrics(
                        oos_group,
                        [item for item in outcomes if item.observation_id in oos_ids],
                        candidate,
                        config.selection_horizon,
                        config.bootstrap_samples,
                        config.bootstrap_block_size,
                    ),
                }
            )
        unique_oos = {item.id: item for item in fold_oos_groups}
        oos_metrics = evaluate_metrics(
            list(unique_oos.values()),
            [item for item in outcomes if item.observation_id in unique_oos],
            candidate,
            config.selection_horizon,
            config.bootstrap_samples,
            config.bootstrap_block_size,
        )
        validation_metrics = metrics["validation"]
        reasons = []
        if validation_metrics["signal_count"] < config.minimum_global:
            reasons.append("échantillon_validation_insuffisant")
        if validation_metrics["symbol_count"] < config.minimum_symbols:
            reasons.append("dépendance_symboles")
        if validation_metrics["calendar_periods"] < config.minimum_calendar_periods:
            reasons.append("couverture_calendaire_insuffisante")
        if any(
            cast(dict[str, Any], item["validation"])["signal_count"] < config.minimum_per_fold
            for item in fold_metrics
        ):
            reasons.append("échantillon_fold_insuffisant")
        if (
            validation_metrics["timeframe_count"]
            and validation_metrics["minimum_timeframe_count"] < config.minimum_per_timeframe
        ):
            reasons.append("insufficient_timeframe_sample")
        concentration_limit = config.promotion_criteria["max_symbol_concentration"]
        if validation_metrics["max_symbol_concentration"] > concentration_limit:
            reasons.append("concentration_symbole")
        if validation_metrics["net_median"] is None or validation_metrics["net_median"] < 0:
            reasons.append("performance_nette_validation_négative")
        train_median = metrics["train"]["net_median"]
        validation_median = validation_metrics["net_median"]
        degradation = (
            train_median - validation_median
            if train_median is not None and validation_median is not None
            else math.inf
        )
        if degradation > config.promotion_criteria["max_validation_degradation"]:
            reasons.append("excessive_validation_degradation")
        robust_score = (
            validation_median
            - max(0.0, degradation)
            - validation_metrics["max_symbol_concentration"] * 0.001
            if validation_median is not None
            else None
        )
        neighbors: list[dict[str, Any]] = []
        if candidate.rsi_threshold is not None:
            for value in sorted(
                {
                    max(0.0, candidate.rsi_threshold - 2),
                    min(100.0, candidate.rsi_threshold + 2),
                }
            ):
                neighbor = candidate.model_copy(update={"rsi_threshold": value})
                neighbor_metrics = evaluate_metrics(
                    splits["validation"],
                    [item for item in outcomes if item.observation_id in outcome_ids["validation"]],
                    neighbor,
                    config.selection_horizon,
                    config.bootstrap_samples,
                    config.bootstrap_block_size,
                )
                neighbors.append(
                    {
                        "parameter": "rsi_threshold",
                        "value": value,
                        "signal_count": neighbor_metrics["signal_count"],
                        "net_median": neighbor_metrics["net_median"],
                    }
                )
        if candidate.min_confluence_score is not None:
            for value in sorted(
                {
                    max(0.0, candidate.min_confluence_score - 5),
                    min(100.0, candidate.min_confluence_score + 5),
                }
            ):
                neighbor = candidate.model_copy(update={"min_confluence_score": value})
                neighbor_metrics = evaluate_metrics(
                    splits["validation"],
                    [item for item in outcomes if item.observation_id in outcome_ids["validation"]],
                    neighbor,
                    config.selection_horizon,
                    config.bootstrap_samples,
                    config.bootstrap_block_size,
                )
                neighbors.append(
                    {
                        "parameter": "min_confluence_score",
                        "value": value,
                        "signal_count": neighbor_metrics["signal_count"],
                        "net_median": neighbor_metrics["net_median"],
                    }
                )
        for factor, weight in sorted(candidate.weights.items()):
            for value in sorted({max(0, weight - 5), min(40, weight + 5)}):
                if value == weight:
                    continue
                neighbor = candidate.model_copy(
                    update={"weights": {**candidate.weights, factor: value}}
                )
                neighbor_metrics = evaluate_metrics(
                    splits["validation"],
                    [item for item in outcomes if item.observation_id in outcome_ids["validation"]],
                    neighbor,
                    config.selection_horizon,
                    config.bootstrap_samples,
                    config.bootstrap_block_size,
                )
                neighbors.append(
                    {
                        "parameter": f"weight.{factor}",
                        "value": value,
                        "signal_count": neighbor_metrics["signal_count"],
                        "net_median": neighbor_metrics["net_median"],
                    }
                )
        neighbor_medians = [
            float(item["net_median"]) for item in neighbors if item["net_median"] is not None
        ]
        local_variation = (
            max(neighbor_medians) - min(neighbor_medians) if len(neighbor_medians) > 1 else 0.0
        )
        if local_variation > config.promotion_criteria["max_local_sensitivity"]:
            reasons.append("sensibilité_locale_excessive")
        results.append(
            CandidateResult(
                candidate_id=candidate.id,
                family=candidate.family,
                eligible=not reasons,
                rejection_reasons=reasons,
                metrics=metrics,
                walk_forward=fold_metrics,
                sensitivity={
                    "neighbors": neighbors,
                    "net_median_range": local_variation,
                    "stable": local_variation <= config.promotion_criteria["max_local_sensitivity"],
                    "cost_scenarios": [
                        {
                            "bps": bps,
                            "net_mean": (
                                validation_metrics["gross_mean"] - bps / 10_000
                                if validation_metrics["gross_mean"] is not None
                                else None
                            ),
                        }
                        for bps in config.cost_scenarios_bps
                    ],
                },
                robust_score=robust_score,
                oos_metrics=oos_metrics,
                final_test_metrics=metrics["test"],
            )
        )
    specs = {item.id: item for item in config.candidates}
    selected_oos: dict[str, list[SignalObservation]] = defaultdict(list)
    for fold_index, (_, _, oos_group) in enumerate(folds):
        contenders: list[tuple[float, CandidateResult]] = []
        for item in results:
            validation = item.walk_forward[fold_index]["validation"]
            median = validation.get("net_median")
            if (
                isinstance(median, (int, float))
                and validation.get("signal_count", 0) >= config.minimum_per_fold
            ):
                contenders.append((float(median), item))
        winner = max(contenders, key=lambda entry: entry[0])[1] if contenders else None
        for item in results:
            item.walk_forward[fold_index]["selected_for_oos"] = bool(
                winner and item.candidate_id == winner.candidate_id
            )
        if winner:
            selected_oos[winner.candidate_id].extend(oos_group)
    for item in results:
        selected = {observation.id: observation for observation in selected_oos[item.candidate_id]}
        item.oos_metrics = evaluate_metrics(
            list(selected.values()),
            [outcome for outcome in outcomes if outcome.observation_id in selected],
            specs[item.candidate_id],
            config.selection_horizon,
            config.bootstrap_samples,
            config.bootstrap_block_size,
        )
        item.oos_metrics["selected_fold_count"] = sum(
            bool(fold.get("selected_for_oos")) for fold in item.walk_forward
        )
    adjusted = _benjamini_hochberg(
        [
            float(item.metrics["validation"].get("bootstrap", {}).get("p_nonpositive") or 1.0)
            for item in results
        ]
    )
    for item, adjusted_p in zip(results, adjusted, strict=True):
        item.adjusted_p_value = adjusted_p
        if item.robust_score is not None:
            item.robust_score *= max(0.0, 1.0 - adjusted_p)
    eligible = sorted(
        (item for item in results if item.eligible),
        key=lambda item: item.robust_score if item.robust_score is not None else -math.inf,
        reverse=True,
    )
    for rank, item in enumerate(eligible, 1):
        item.rank = rank
        item.selected = rank <= 3
        item.selection_reason = (
            f"rank {rank}: robust validation score, "
            f"Benjamini-Hochberg={item.adjusted_p_value:.4f}"
        )
    return results, windows
