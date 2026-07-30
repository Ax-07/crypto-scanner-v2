"""Contrats, causalité et stages de l'expérience RSI Phase 7.2."""

from __future__ import annotations

import inspect
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.experiments import rsi_filter_v1 as experiment
from app.models.backtest import SignalObservation

PROJECT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT / "docs" / "audits" / "rsi-filter-experiment-v1-plan.md"


def _observation(*, rsi: float | None, status: str = "available") -> SignalObservation:
    source = experiment.prepare_quick()[0].observations[1]
    return source.model_copy(
        update={
            "rsi": rsi,
            "availability": {**source.availability, "rsi": status},
        },
        deep=True,
    )


def test_manifest_variants_deltas_datasets_segments_and_hash_are_stable() -> None:
    payload = experiment.load_manifest(MANIFEST)
    assert [item["id"] for item in payload["variants"]] == ["R0", "R1", "R2", "R3"]
    assert [item["delta"] for item in payload["variants"]] == ["0", "5", "10", None]
    assert experiment.manifest_hash(MANIFEST) == (
        "sha256:e928998ad8f71429f85db51d3975dc6c46ec3a62f868ba407e5080f84f18ad64"
    )
    assert [
        (item["symbol"], item["timeframe"], item["candles"]) for item in payload["datasets"]
    ] == [
        ("BTC/USDC", "4h", 7381),
        ("BTC/USDC", "1d", 1384),
        ("LINK/USDC", "4h", 1208),
        ("ONDO/USDC", "1h", 1500),
        ("SUI/USDC", "1h", 1500),
    ]
    for item in payload["datasets"]:
        assert item["segments"]["development"]["start_index"] == 0
        assert item["segments"]["development"]["end_index"] == int(item["candles"] * 0.60)
        assert item["segments"]["validation"]["end_index"] == int(item["candles"] * 0.80)
        assert item["segments"]["test"]["end_index"] == item["candles"]


def test_manifest_detects_modification_unknown_version_variant_and_missing_threshold(
    tmp_path: Path,
) -> None:
    payload = experiment.load_manifest(MANIFEST)
    payload["version"] = "unknown"
    with pytest.raises(experiment.ExperimentInvalidated, match="version"):
        experiment.validate_manifest(payload)
    payload = experiment.load_manifest(MANIFEST)
    payload["variants"][1]["id"] = "RX"
    with pytest.raises(experiment.ExperimentInvalidated, match="variantes"):
        experiment.validate_manifest(payload)
    payload = experiment.load_manifest(MANIFEST)
    payload["variants"][1]["threshold"] = None
    with pytest.raises(experiment.ExperimentInvalidated, match="seuil"):
        experiment.validate_manifest(payload)
    changed = tmp_path / "plan.md"
    changed.write_bytes(MANIFEST.read_bytes() + b"\n")
    assert experiment.manifest_hash(changed) != experiment.manifest_hash(MANIFEST)


@pytest.mark.parametrize(
    ("operator", "threshold", "delta", "expected"),
    [
        ("<", "35", "5", "40"),
        ("<=", "98", "10", "100"),
        (">", "30", "5", "25"),
        (">=", "2", "10", "0"),
    ],
)
def test_relaxation_preserves_operator_and_clamps(
    operator: str, threshold: str, delta: str, expected: str
) -> None:
    assert experiment.relax_threshold(operator, Decimal(threshold), Decimal(delta)) == Decimal(
        expected
    )


def test_rsi_acceptance_is_monotone_for_every_valid_integer() -> None:
    for value in range(101):
        observation = _observation(rsi=float(value))
        decisions = [
            experiment.rsi_filter_passes(observation, experiment.VARIANTS[name])
            for name in ("R0", "R1", "R2")
        ]
        assert not decisions[0] or decisions[1]
        assert not decisions[1] or decisions[2]
        assert experiment.rsi_filter_passes(observation, experiment.VARIANTS["R3"])


@pytest.mark.parametrize("status", ["insufficient_data", "invalid_data", "disabled"])
def test_unavailable_status_is_not_relaxed(status: str) -> None:
    observation = _observation(rsi=20, status=status)
    assert not any(
        experiment.rsi_filter_passes(observation, experiment.VARIANTS[name])
        for name in experiment.VARIANT_ORDER
    )


def test_r0_parity_and_all_non_rsi_inputs_are_identical() -> None:
    canonical = experiment.prepare_quick()[0].observations
    variants = {
        name: tuple(experiment.apply_variant(item, experiment.VARIANTS[name]) for item in canonical)
        for name in experiment.VARIANT_ORDER
    }
    experiment.assert_variant_invariants(canonical, variants)
    for original, r0 in zip(canonical, variants["R0"], strict=True):
        assert (r0.accepted, r0.rejection_stage, r0.filter_trace) == (
            original.accepted,
            original.rejection_stage,
            original.filter_trace,
        )


def test_counterfactual_matrix_does_not_short_circuit_and_counts_rsi_only() -> None:
    observation = _observation(rsi=50)
    matrix = experiment.counterfactual_filter_matrix(observation, experiment.VARIANTS["R0"])
    assert matrix == {
        "rsi": False,
        "trend": True,
        "signal_filters": True,
        "confluence": True,
    }
    evaluated = experiment.apply_variant(observation, experiment.VARIANTS["R0"])
    funnel = experiment._funnel((evaluated,), experiment.VARIANTS["R0"])
    assert funnel["rsi_only_rejections"] == 1
    assert funnel["first_rejection_stages"] == {"rsi": 1}


def test_future_rsi_change_cannot_change_past_decision_anti_lookahead() -> None:
    observations = list(experiment.prepare_quick()[0].observations[:3])
    before = experiment.apply_variant(observations[0], experiment.VARIANTS["R2"])
    observations[2] = observations[2].model_copy(update={"rsi": 0.0})
    after = experiment.apply_variant(observations[0], experiment.VARIANTS["R2"])
    assert before == after


def test_sequence_relaxation_can_extend_and_merge_without_pyramiding() -> None:
    prepared = experiment.prepare_quick()[0]
    r0 = tuple(
        experiment.apply_variant(item, experiment.VARIANTS["R0"]) for item in prepared.observations
    )
    r3 = tuple(
        experiment.apply_variant(item, experiment.VARIANTS["R3"]) for item in prepared.observations
    )
    assert sum(item.accepted for item in r3) > sum(item.accepted for item in r0)
    result = experiment.simulate_portfolio(
        symbol=prepared.selection.symbol,
        steps=experiment._variant_steps(prepared.steps, r3),
        config=prepared.portfolio_config,
    )
    assert result.metrics.open_position_count == 0
    assert all(trade.exit_time > trade.entry_time for trade in result.trades)
    assert len({trade.position_id for trade in result.trades}) == len(result.trades)


def test_development_and_validation_never_expose_test_metrics(tmp_path: Path) -> None:
    cache = tmp_path / "cache.pkl.gz"
    experiment.run_stage(
        stage="reproduce",
        mode="quick",
        database_path=tmp_path / "unused.sqlite3",
        output=tmp_path,
        manifest_path=MANIFEST,
        cache_path=cache,
    )
    development = experiment.run_stage(
        stage="development",
        mode="quick",
        database_path=tmp_path / "unused.sqlite3",
        output=tmp_path,
        manifest_path=MANIFEST,
        cache_path=cache,
    )
    validation = experiment.run_stage(
        stage="validation",
        mode="quick",
        database_path=tmp_path / "unused.sqlite3",
        output=tmp_path,
        manifest_path=MANIFEST,
        cache_path=cache,
    )
    serialized = json.dumps([development, validation], default=str)
    assert '"test"' not in serialized
    assert '"final-test"' not in serialized
    assert development["variants_executed"] == ["R0", "R1", "R2", "R3"]
    assert validation["variants_executed"][0] == "R0"
    assert set(validation["variants_executed"][1:]) == set(development["survivors"])


def test_quick_stages_are_reproducible_outside_runtime_metadata(tmp_path: Path) -> None:
    outputs = []
    for run in ("first", "second"):
        output = tmp_path / run
        cache = output / "cache.pkl.gz"
        stages = []
        for stage in ("reproduce", "development", "validation"):
            stages.append(
                experiment.run_stage(
                    stage=stage,
                    mode="quick",
                    database_path=tmp_path / "unused.sqlite3",
                    output=output,
                    manifest_path=MANIFEST,
                    cache_path=cache,
                )
            )
        for item in stages:
            item.pop("duration_seconds", None)
        outputs.append(stages)
    assert outputs[0] == outputs[1]


def test_final_guard_rejects_absent_multiple_unknown_and_tampered_selection() -> None:
    digest = experiment.manifest_hash(MANIFEST)
    validation = {
        "stage": "validation",
        "manifest_hash": digest,
        "variants_executed": ["R0", "R1"],
        "selected_variant": "R1",
    }
    selection = {
        "manifest_hash": digest,
        "baseline_fingerprint": experiment.BASELINE_FINGERPRINT,
        "selected_variant": "R1",
    }
    for selected in ((), ("R1", "R2"), ("RX",)):
        with pytest.raises(experiment.ExperimentInvalidated):
            experiment.guard_final_test(
                manifest_path=MANIFEST,
                manifest_digest=digest,
                selected_variants=selected,
                selection=selection,
                validation=validation,
            )
    with pytest.raises(experiment.ExperimentInvalidated, match="sélection"):
        experiment.guard_final_test(
            manifest_path=MANIFEST,
            manifest_digest=digest,
            selected_variants=("R1",),
            selection={**selection, "selected_variant": "R2"},
            validation=validation,
        )
    assert (
        experiment.guard_final_test(
            manifest_path=MANIFEST,
            manifest_digest=digest,
            selected_variants=("R1",),
            selection=selection,
            validation=validation,
        )
        == "R1"
    )


def test_experiment_has_no_network_or_runtime_import() -> None:
    source = inspect.getsource(experiment)
    assert "import ccxt" not in source
    assert "import requests" not in source
    assert "import httpx" not in source
    assert "ForwardOutcome" in source
    assert "outcome" not in inspect.signature(experiment.apply_variant).parameters


def test_manifest_segments_match_chronological_function_exactly() -> None:
    manifest = experiment.load_manifest(MANIFEST)
    for item in manifest["datasets"]:
        start = experiment.datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
        hours = {"1h": 1, "4h": 4, "1d": 24}[item["timeframe"]]
        timestamps = [start + timedelta(hours=index * hours) for index in range(item["candles"])]
        actual = experiment.chronological_segments(timestamps)
        for segment in actual:
            expected = item["segments"][segment.name]
            assert (segment.start_index, segment.end_index) == (
                expected["start_index"],
                expected["end_index"],
            )
