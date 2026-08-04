from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.domain.ml_walk_forward import (
    MLWalkForwardError,
    build_expanding_walk_forward_plan,
)
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)

BASE_TIME = datetime(
    2026,
    1,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)


def dataset_row(
    observation_id: int,
    *,
    decision_time: datetime,
    symbol: str = "BTC/USDC",
    job_id: str = "walk-forward-test",
) -> MLDatasetRow:
    """Construit une ligne ML neutre valide."""
    return MLDatasetRow(
        observation_id=observation_id,
        job_id=job_id,
        symbol=symbol,
        timeframe="1h",
        decision_time=decision_time,
        source_open_time=(decision_time - timedelta(hours=1)),
        snapshot_status="confirmed",
        calculation_mode="canonical",
        source_algorithm_version=("signal-evaluation-v3"),
        source_dataset_version=("binance-history-v1"),
        profile_id="inline",
        profile_fingerprint="sha256:profile",
        horizon=6,
        entry_policy="signal_close",
        entry_time=decision_time,
        exit_time=(decision_time + timedelta(hours=6)),
        natr_percent=2.0,
        natr_multiplier=1.0,
        neutral_threshold_return=0.02,
        future_return=0.0,
        label=MarketDirectionLabel.NEUTRAL,
        features={
            "price.close": (100.0 + observation_id),
        },
    )


def hourly_rows(
    count: int,
    *,
    job_id: str = "walk-forward-test",
) -> tuple[MLDatasetRow, ...]:
    """Construit une série horaire continue."""
    return tuple(
        dataset_row(
            index + 1,
            decision_time=(BASE_TIME + timedelta(hours=index)),
            job_id=job_id,
        )
        for index in range(count)
    )


def test_builds_expected_expanding_folds() -> None:
    rows = hourly_rows(600)

    plan = build_expanding_walk_forward_plan(
        rows,
        evaluation_end=(BASE_TIME + timedelta(hours=550)),
        fold_count=3,
        validation_window=50,
        minimum_train_window=200,
    )

    assert plan.source_row_count == 600
    assert plan.eligible_row_count == 544

    assert plan.excluded_at_or_after_evaluation_end == 50
    assert plan.excluded_target_overlap_count == 6

    assert plan.fold_count == 3
    assert plan.validation_row_count == 150

    assert [fold.train_row_count for fold in plan.folds] == [
        388,
        438,
        488,
    ]

    assert [fold.validation_row_count for fold in plan.folds] == [
        50,
        50,
        50,
    ]

    assert [fold.purged_before_validation for fold in plan.folds] == [
        6,
        6,
        6,
    ]

    assert [fold.validation_start for fold in plan.folds] == [
        BASE_TIME + timedelta(hours=394),
        BASE_TIME + timedelta(hours=444),
        BASE_TIME + timedelta(hours=494),
    ]

    assert [fold.validation_end for fold in plan.folds] == [
        BASE_TIME + timedelta(hours=443),
        BASE_TIME + timedelta(hours=493),
        BASE_TIME + timedelta(hours=543),
    ]

    assert [fold.validation_rows[0].observation_id for fold in plan.folds] == [
        395,
        445,
        495,
    ]

    assert [fold.validation_rows[-1].observation_id for fold in plan.folds] == [
        444,
        494,
        544,
    ]


def test_build_sorts_reversed_source_rows() -> None:
    rows = hourly_rows(600)

    ordered_plan = build_expanding_walk_forward_plan(
        rows,
        evaluation_end=(BASE_TIME + timedelta(hours=550)),
        fold_count=3,
        validation_window=50,
        minimum_train_window=200,
    )
    reversed_plan = build_expanding_walk_forward_plan(
        tuple(reversed(rows)),
        evaluation_end=(BASE_TIME + timedelta(hours=550)),
        fold_count=3,
        validation_window=50,
        minimum_train_window=200,
    )

    assert [[row.observation_id for row in fold.train_rows] for fold in ordered_plan.folds] == [
        [row.observation_id for row in fold.train_rows] for fold in reversed_plan.folds
    ]

    assert [
        [row.observation_id for row in fold.validation_rows] for fold in ordered_plan.folds
    ] == [[row.observation_id for row in fold.validation_rows] for fold in reversed_plan.folds]


def test_boundaries_use_unique_decision_times() -> None:
    rows: list[MLDatasetRow] = []
    observation_id = 1

    for hour in range(300):
        decision_time = BASE_TIME + timedelta(hours=hour)

        for symbol in (
            "BTC/USDC",
            "ETH/USDC",
        ):
            rows.append(
                dataset_row(
                    observation_id,
                    decision_time=decision_time,
                    symbol=symbol,
                )
            )
            observation_id += 1

    plan = build_expanding_walk_forward_plan(
        tuple(reversed(rows)),
        evaluation_end=(BASE_TIME + timedelta(hours=280)),
        fold_count=2,
        validation_window=30,
        minimum_train_window=200,
    )

    assert plan.source_row_count == 600
    assert plan.eligible_row_count == 548

    assert plan.excluded_at_or_after_evaluation_end == 40
    assert plan.excluded_target_overlap_count == 12

    assert [fold.train_row_count for fold in plan.folds] == [
        416,
        476,
    ]

    assert [fold.validation_row_count for fold in plan.folds] == [
        60,
        60,
    ]

    assert [fold.purged_before_validation for fold in plan.folds] == [
        12,
        12,
    ]

    for fold in plan.folds:
        first_validation_time = fold.validation_start

        assert {
            row.symbol for row in fold.validation_rows if row.decision_time == first_validation_time
        } == {
            "BTC/USDC",
            "ETH/USDC",
        }


def test_plan_excludes_test_and_overlapping_targets() -> None:
    evaluation_end = BASE_TIME + timedelta(hours=550)

    plan = build_expanding_walk_forward_plan(
        hourly_rows(600),
        evaluation_end=evaluation_end,
        fold_count=3,
        validation_window=50,
        minimum_train_window=200,
    )

    development_rows = tuple(
        row for fold in plan.folds for row in (fold.train_rows + fold.validation_rows)
    )

    assert development_rows

    assert all(row.decision_time < evaluation_end for row in development_rows)

    assert all(row.exit_time < evaluation_end for row in development_rows)


def test_validation_folds_are_disjoint() -> None:
    plan = build_expanding_walk_forward_plan(
        hourly_rows(600),
        evaluation_end=(BASE_TIME + timedelta(hours=550)),
        fold_count=3,
        validation_window=50,
        minimum_train_window=200,
    )

    validation_ids = [row.observation_id for fold in plan.folds for row in fold.validation_rows]

    assert len(validation_ids) == 150
    assert len(set(validation_ids)) == 150


def test_each_train_is_purged_before_validation() -> None:
    plan = build_expanding_walk_forward_plan(
        hourly_rows(600),
        evaluation_end=(BASE_TIME + timedelta(hours=550)),
        fold_count=3,
        validation_window=50,
        minimum_train_window=200,
    )

    for fold in plan.folds:
        assert fold.train_rows[-1].exit_time < fold.validation_start

        assert all(row.decision_time < fold.validation_start for row in fold.train_rows)

        assert all(
            fold.validation_start <= row.decision_time <= fold.validation_end
            for row in fold.validation_rows
        )


@pytest.mark.parametrize(
    (
        "fold_count",
        "validation_window",
        "minimum_train_window",
        "expected_name",
    ),
    [
        (
            0,
            10,
            20,
            "fold_count",
        ),
        (
            -1,
            10,
            20,
            "fold_count",
        ),
        (
            True,
            10,
            20,
            "fold_count",
        ),
        (
            2,
            0,
            20,
            "validation_window",
        ),
        (
            2,
            -1,
            20,
            "validation_window",
        ),
        (
            2,
            10,
            False,
            "minimum_train_window",
        ),
    ],
)
def test_rejects_invalid_positive_integers(
    fold_count: int,
    validation_window: int,
    minimum_train_window: int,
    expected_name: str,
) -> None:
    with pytest.raises(
        MLWalkForwardError,
        match=expected_name,
    ):
        build_expanding_walk_forward_plan(
            hourly_rows(100),
            evaluation_end=(BASE_TIME + timedelta(hours=90)),
            fold_count=fold_count,
            validation_window=validation_window,
            minimum_train_window=(minimum_train_window),
        )


def test_rejects_naive_evaluation_end() -> None:
    with pytest.raises(
        MLWalkForwardError,
        match="timezone-aware",
    ):
        build_expanding_walk_forward_plan(
            hourly_rows(100),
            evaluation_end=datetime(
                2026,
                1,
                4,
                0,
                0,
            ),
            fold_count=2,
            validation_window=10,
            minimum_train_window=20,
        )


def test_rejects_non_utc_evaluation_end() -> None:
    paris_timezone = timezone(timedelta(hours=1))

    with pytest.raises(
        MLWalkForwardError,
        match="exprimé en UTC",
    ):
        build_expanding_walk_forward_plan(
            hourly_rows(100),
            evaluation_end=datetime(
                2026,
                1,
                4,
                0,
                0,
                tzinfo=paris_timezone,
            ),
            fold_count=2,
            validation_window=10,
            minimum_train_window=20,
        )


def test_rejects_empty_dataset() -> None:
    with pytest.raises(
        MLWalkForwardError,
        match="ne peut pas être vide",
    ):
        build_expanding_walk_forward_plan(
            (),
            evaluation_end=(BASE_TIME + timedelta(hours=100)),
            fold_count=2,
            validation_window=10,
            minimum_train_window=20,
        )


def test_rejects_duplicate_observations() -> None:
    rows = list(hourly_rows(100))
    rows[-1] = rows[-1].model_copy(
        update={
            "observation_id": 1,
        }
    )

    with pytest.raises(
        MLWalkForwardError,
        match="plusieurs lignes",
    ):
        build_expanding_walk_forward_plan(
            tuple(rows),
            evaluation_end=(BASE_TIME + timedelta(hours=90)),
            fold_count=2,
            validation_window=10,
            minimum_train_window=20,
        )


def test_rejects_multiple_jobs() -> None:
    rows = list(hourly_rows(100))
    rows[-1] = rows[-1].model_copy(
        update={
            "job_id": "other-job",
        }
    )

    with pytest.raises(
        MLWalkForwardError,
        match="même job",
    ):
        build_expanding_walk_forward_plan(
            tuple(rows),
            evaluation_end=(BASE_TIME + timedelta(hours=90)),
            fold_count=2,
            validation_window=10,
            minimum_train_window=20,
        )


def test_rejects_multiple_horizons() -> None:
    rows = list(hourly_rows(100))
    rows[-1] = rows[-1].model_copy(
        update={
            "horizon": 12,
        }
    )

    with pytest.raises(
        MLWalkForwardError,
        match="même horizon",
    ):
        build_expanding_walk_forward_plan(
            tuple(rows),
            evaluation_end=(BASE_TIME + timedelta(hours=90)),
            fold_count=2,
            validation_window=10,
            minimum_train_window=20,
        )


def test_rejects_insufficient_decision_times() -> None:
    with pytest.raises(
        MLWalkForwardError,
        match="temps de décision insuffisant",
    ):
        build_expanding_walk_forward_plan(
            hourly_rows(100),
            evaluation_end=(BASE_TIME + timedelta(hours=90)),
            fold_count=4,
            validation_window=20,
            minimum_train_window=20,
        )
