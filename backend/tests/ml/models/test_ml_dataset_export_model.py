from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.ml.models.ml_dataset_export import (
    MLDatasetExportManifest,
    MLDatasetExportStats,
)

FIRST_TIME = datetime(
    2026,
    1,
    1,
    12,
    0,
    tzinfo=timezone.utc,
)
LAST_TIME = FIRST_TIME + timedelta(hours=12)

VALID_SHA256 = "sha256:" + ("a" * 64)


def valid_stats(
    **changes: object,
) -> MLDatasetExportStats:
    """Construit des statistiques d'export cohérentes."""
    values: dict[str, object] = {
        "source_rows": 5,
        "processed_rows": 5,
        "generated_rows": 3,
        "skipped_rows": 2,
        "censored_outcomes": 1,
        "invalid_outcomes": 0,
        "missing_natr": 0,
        "contract_rejections": 1,
        "batch_count": 2,
        "rejection_reasons": {
            "gross_return est requis": 1,
        },
    }
    values.update(changes)
    return MLDatasetExportStats.model_validate(values)


def valid_manifest(
    **changes: object,
) -> MLDatasetExportManifest:
    """Construit un manifeste JSONL valide."""
    values: dict[str, object] = {
        "source_job_id": "backtest-ml-v1",
        "horizon": 6,
        "natr_multiplier": 1.0,
        "data_file": "backtest-ml-v1.jsonl",
        "data_sha256": VALID_SHA256,
        "row_count": 3,
        "first_decision_time": FIRST_TIME,
        "last_decision_time": LAST_TIME,
        "feature_names": [
            "price.close",
            "indicator.atr.raw_value",
        ],
        "source_algorithm_versions": [
            "signal-evaluation-v3",
        ],
        "source_dataset_versions": [
            "binance-history-v1",
        ],
        "profile_ids": [
            "inline",
        ],
        "profile_fingerprints": [
            "sha256:profile",
        ],
        "stats": valid_stats(),
    }
    values.update(changes)
    return MLDatasetExportManifest.model_validate(values)


def test_valid_manifest_exposes_versioned_contract() -> None:
    manifest = valid_manifest()

    assert manifest.manifest_schema_version == 1
    assert manifest.export_format == "jsonl"
    assert manifest.dataset_schema_version == 1
    assert manifest.feature_schema_version == "causal-features-v1"
    assert manifest.label_schema_version == "direction-natr-h6-v1"
    assert manifest.horizon == 6


def test_manifest_normalizes_required_strings() -> None:
    manifest = valid_manifest(
        source_job_id="  backtest-ml-v1  ",
        data_file="  dataset.jsonl  ",
    )

    assert manifest.source_job_id == "backtest-ml-v1"
    assert manifest.data_file == "dataset.jsonl"


def test_manifest_normalizes_sorted_unique_collections() -> None:
    manifest = valid_manifest(
        feature_names=[
            "z.feature",
            " a.feature ",
            "z.feature",
            "",
        ],
        source_algorithm_versions=[
            "signal-evaluation-v3",
            " signal-evaluation-v3 ",
        ],
        profile_ids=[
            "profile-b",
            "profile-a",
            "profile-b",
        ],
    )

    assert manifest.feature_names == [
        "a.feature",
        "z.feature",
    ]
    assert manifest.source_algorithm_versions == [
        "signal-evaluation-v3",
    ]
    assert manifest.profile_ids == [
        "profile-a",
        "profile-b",
    ]


def test_manifest_normalizes_datetimes_to_utc() -> None:
    local_timezone = timezone(timedelta(hours=2))

    manifest = valid_manifest(
        first_decision_time=FIRST_TIME.astimezone(local_timezone),
        last_decision_time=LAST_TIME.astimezone(local_timezone),
    )

    assert manifest.first_decision_time is not None
    assert manifest.last_decision_time is not None
    assert manifest.first_decision_time.tzinfo is timezone.utc
    assert manifest.last_decision_time.tzinfo is timezone.utc
    assert manifest.first_decision_time == FIRST_TIME
    assert manifest.last_decision_time == LAST_TIME


def test_empty_dataset_accepts_no_temporal_bounds() -> None:
    stats = valid_stats(
        source_rows=0,
        processed_rows=0,
        generated_rows=0,
        skipped_rows=0,
        censored_outcomes=0,
        invalid_outcomes=0,
        missing_natr=0,
        contract_rejections=0,
        batch_count=0,
        rejection_reasons={},
    )

    manifest = valid_manifest(
        row_count=0,
        first_decision_time=None,
        last_decision_time=None,
        feature_names=[],
        stats=stats,
    )

    assert manifest.row_count == 0
    assert manifest.first_decision_time is None
    assert manifest.last_decision_time is None


def test_non_empty_dataset_requires_temporal_bounds() -> None:
    with pytest.raises(
        ValidationError,
        match="dataset non vide",
    ):
        valid_manifest(
            first_decision_time=None,
        )


def test_empty_dataset_rejects_temporal_bounds() -> None:
    stats = valid_stats(
        source_rows=0,
        processed_rows=0,
        generated_rows=0,
        skipped_rows=0,
        censored_outcomes=0,
        invalid_outcomes=0,
        missing_natr=0,
        contract_rejections=0,
        batch_count=0,
        rejection_reasons={},
    )

    with pytest.raises(
        ValidationError,
        match="dataset vide",
    ):
        valid_manifest(
            row_count=0,
            stats=stats,
        )


def test_first_time_cannot_follow_last_time() -> None:
    with pytest.raises(
        ValidationError,
        match="first_decision_time",
    ):
        valid_manifest(
            first_decision_time=LAST_TIME,
            last_decision_time=FIRST_TIME,
        )


def test_row_count_must_match_generated_rows() -> None:
    with pytest.raises(
        ValidationError,
        match="row_count",
    ):
        valid_manifest(
            row_count=4,
        )


def test_manifest_rejects_naive_datetime() -> None:
    with pytest.raises(
        ValidationError,
        match="fuseau horaire",
    ):
        valid_manifest(
            first_decision_time=FIRST_TIME.replace(tzinfo=None),
        )


@pytest.mark.parametrize(
    "invalid_sha256",
    [
        "",
        "a" * 64,
        "sha256:abc",
        "sha256:" + ("A" * 64),
        "md5:" + ("a" * 64),
    ],
)
def test_manifest_rejects_invalid_sha256(
    invalid_sha256: str,
) -> None:
    with pytest.raises(ValidationError):
        valid_manifest(
            data_sha256=invalid_sha256,
        )


def test_stats_normalize_rejection_reasons() -> None:
    stats = valid_stats(
        generated_rows=2,
        contract_rejections=2,
        skipped_rows=3,
        rejection_reasons={
            " z reason ": 1,
            "a reason": 1,
        },
    )

    assert stats.rejection_reasons == {
        "a reason": 1,
        "z reason": 1,
    }


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "skipped_rows": 3,
            },
            "skipped_rows",
        ),
        (
            {
                "processed_rows": 6,
            },
            "generated_rows",
        ),
        (
            {
                "source_rows": 6,
            },
            "processed_rows",
        ),
        (
            {
                "generated_rows": 2,
                "skipped_rows": 3,
                "contract_rejections": 2,
            },
            "rejection_reasons",
        ),
    ],
)
def test_stats_reject_inconsistent_counters(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match=message,
    ):
        valid_stats(**changes)


@pytest.mark.parametrize(
    "rejection_reasons",
    [
        {
            "": 1,
        },
        {
            "   ": 1,
        },
        {
            "invalid": 0,
        },
        {
            "invalid": -1,
        },
    ],
)
def test_stats_reject_invalid_rejection_reasons(
    rejection_reasons: dict[str, int],
) -> None:
    with pytest.raises(ValidationError):
        valid_stats(
            rejection_reasons=rejection_reasons,
        )
