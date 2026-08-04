from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pytest

from app.ml.cli.export_ml_benchmark import (
    DEFAULT_C_VALUES,
    _build_parser,
    _parse_utc_datetime,
    _validate_selected_candidate,
)
from app.ml.domain.ml_feature_policy import (
    MLFeaturePolicy,
)

UTC = timezone.utc


def valid_arguments() -> list[str]:
    """Retourne les arguments minimaux valides."""
    return [
        "dataset.manifest.json",
        "--benchmark-name",
        "btc-usdc-1h-h6-logistic-v1",
        "--file-stem",
        "btc-usdc-1h-h6-logistic-v1-rejected",
        "--created-at",
        "2026-08-03T23:23:00+02:00",
        "--selected-policy",
        "normalized_deduplicated",
        "--selected-c-value",
        "0.03",
    ]


def test_parse_utc_datetime_accepts_z_suffix() -> None:
    parsed = _parse_utc_datetime("2026-08-03T21:23:00Z")

    assert parsed == datetime(
        2026,
        8,
        3,
        21,
        23,
        tzinfo=UTC,
    )


def test_parse_utc_datetime_normalizes_offset() -> None:
    parsed = _parse_utc_datetime("2026-08-03T23:23:00+02:00")

    assert parsed == datetime(
        2026,
        8,
        3,
        21,
        23,
        tzinfo=UTC,
    )


def test_parse_utc_datetime_strips_outer_spaces() -> None:
    parsed = _parse_utc_datetime("  2026-08-03T21:23:00Z  ")

    assert parsed == datetime(
        2026,
        8,
        3,
        21,
        23,
        tzinfo=UTC,
    )


def test_parse_utc_datetime_rejects_naive_value() -> None:
    with pytest.raises(
        argparse.ArgumentTypeError,
        match="fuseau horaire",
    ):
        _parse_utc_datetime("2026-08-03T21:23:00")


def test_parse_utc_datetime_rejects_invalid_value() -> None:
    with pytest.raises(
        argparse.ArgumentTypeError,
        match="ISO 8601 valide",
    ):
        _parse_utc_datetime("not-a-date")


def test_parser_accepts_minimum_valid_arguments() -> None:
    arguments = _build_parser().parse_args(valid_arguments())

    assert arguments.manifest_path.name == "dataset.manifest.json"
    assert arguments.benchmark_name == ("btc-usdc-1h-h6-logistic-v1")
    assert arguments.file_stem == ("btc-usdc-1h-h6-logistic-v1-rejected")
    assert arguments.created_at == datetime(
        2026,
        8,
        3,
        21,
        23,
        tzinfo=UTC,
    )
    assert arguments.selected_policy == ("normalized_deduplicated")
    assert arguments.selected_c_value == 0.03

    assert arguments.fold_count == 4
    assert arguments.validation_window == 72
    assert arguments.minimum_train_window == 200
    assert tuple(arguments.candidate_c_values) == DEFAULT_C_VALUES

    assert arguments.status == "rejected"
    assert arguments.decision_reason == []


def test_parser_accepts_repeated_decision_reasons() -> None:
    arguments = _build_parser().parse_args(
        [
            *valid_arguments(),
            "--decision-reason",
            "première raison",
            "--decision-reason",
            "seconde raison",
        ]
    )

    assert arguments.decision_reason == [
        "première raison",
        "seconde raison",
    ]


def test_parser_requires_created_at() -> None:
    arguments = valid_arguments()
    created_at_index = arguments.index("--created-at")

    del arguments[created_at_index : created_at_index + 2]

    with pytest.raises(
        SystemExit,
    ) as error:
        _build_parser().parse_args(arguments)

    assert error.value.code == 2


def test_parser_rejects_unknown_policy() -> None:
    arguments = valid_arguments()
    policy_index = arguments.index("--selected-policy")

    arguments[policy_index + 1] = "unknown-policy"

    with pytest.raises(
        SystemExit,
    ) as error:
        _build_parser().parse_args(arguments)

    assert error.value.code == 2


def test_selected_candidate_accepts_exact_match() -> None:
    _validate_selected_candidate(
        selected_policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
        selected_c_value=0.03,
        best_policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
        best_c_value=0.03,
    )


def test_selected_candidate_accepts_tiny_float_delta() -> None:
    _validate_selected_candidate(
        selected_policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
        selected_c_value=(0.03 + 1e-13),
        best_policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
        best_c_value=0.03,
    )


def test_selected_candidate_rejects_policy_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="politique sélectionnée",
    ):
        _validate_selected_candidate(
            selected_policy=(MLFeaturePolicy.WITHOUT_ABSOLUTE),
            selected_c_value=0.03,
            best_policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
            best_c_value=0.03,
        )


def test_selected_candidate_rejects_c_value_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="valeur de C sélectionnée",
    ):
        _validate_selected_candidate(
            selected_policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
            selected_c_value=0.1,
            best_policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
            best_c_value=0.03,
        )
