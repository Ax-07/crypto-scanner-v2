"""Garanties centrales du protocole expérimental de phase 4."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.experiments import chronological_split, evaluate_candidates, walk_forward_folds
from app.models.backtest import ForwardOutcome, SignalObservation
from app.models.experiment import CandidateSpec, ExperimentConfig, SignalProfileVersion
from app.core.settings import ScanConfig


def observations(count: int = 160) -> list[SignalObservation]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        SignalObservation(
            id=index + 1,
            job_id="source",
            symbol="BTC/USDC" if index % 2 else "ETH/USDC",
            timeframe="4h",
            decision_time=start + timedelta(hours=4 * index),
            accepted=True,
            close=100 + index,
            confluence_factors={"rsi": 0.8, "trend": 0.5},
            availability={"rsi": "available", "trend": "available"},
        )
        for index in range(count)
    ]


def config(**updates) -> ExperimentConfig:
    payload = {
        "source_backtest_id": "source",
        "selection_horizon": 5,
        "split": {"embargo_bars": 5},
        "walk_forward": {"train_bars": 30, "validation_bars": 10, "step_bars": 10, "max_folds": 3},
        "candidates": [{"id": "baseline-v1", "family": "baseline"}],
    }
    payload.update(updates)
    return ExperimentConfig.model_validate(payload)


def test_chronological_splits_apply_embargo_without_overlap() -> None:
    groups, windows = chronological_split(observations(), config())
    assert list(groups) == ["train", "validation", "test"]
    assert windows[0].end < windows[1].start < windows[2].start
    assert len(groups["train"]) == 91
    assert len(groups["validation"]) == 27


def test_embargo_cannot_be_shorter_than_outcome_horizon() -> None:
    with pytest.raises(ValidationError, match="embargo"):
        config(selection_horizon=6)


def test_short_dataset_is_rejected() -> None:
    with pytest.raises(ValueError, match="trop court"):
        chronological_split(observations(10), config())


def test_walk_forward_is_reproducible_and_embargoed() -> None:
    first = walk_forward_folds(observations(), config())
    second = walk_forward_folds(observations(), config())
    assert first == second
    assert len(first) == 3
    assert first[0][0][-1].decision_time < first[0][1][0].decision_time


def test_search_space_is_bounded_and_test_cannot_be_objective() -> None:
    with pytest.raises(ValidationError):
        CandidateSpec(id="bad", weights={"rsi": 41})
    with pytest.raises(ValidationError):
        config(objective_split="test")


def test_published_profile_is_frozen() -> None:
    profile = SignalProfileVersion(
        id="baseline-v1",
        name="Baseline",
        version="1.0.0",
        description="figée",
        signal_config=ScanConfig(),
        dataset_version="fixture-v1",
        code_version="test",
    )
    with pytest.raises(ValidationError):
        profile.version = "2.0.0"


def test_walk_forward_selects_on_validation_before_aggregating_oos() -> None:
    items = observations()
    outcomes = [
        ForwardOutcome(
            observation_id=item.id,
            horizon=5,
            entry_policy="signal_close",
            gross_return=0.01,
            net_return=0.009,
            mfe=0.02,
            mae=-0.005,
        )
        for item in items
    ]
    experiment = config(
        minimum_global=5,
        minimum_symbols=1,
        minimum_calendar_periods=1,
        minimum_per_fold=2,
        candidates=[
            {"id": "baseline-v1", "family": "baseline"},
            {
                "id": "too-strict",
                "family": "thresholds",
                "min_confluence_score": 90,
            },
        ],
    )
    results, _ = evaluate_candidates(experiment, items, outcomes)
    baseline = next(item for item in results if item.candidate_id == "baseline-v1")
    strict = next(item for item in results if item.candidate_id == "too-strict")
    assert all(fold["selected_for_oos"] for fold in baseline.walk_forward)
    assert not any(fold["selected_for_oos"] for fold in strict.walk_forward)
    assert baseline.oos_metrics["selected_fold_count"] == len(baseline.walk_forward)
    assert strict.oos_metrics["signal_count"] == 0
