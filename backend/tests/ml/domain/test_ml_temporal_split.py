from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.domain.ml_temporal_split import (
    MLTemporalSplitError,
    split_ml_dataset_chronologically,
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
    job_id: str = "job-1",
) -> MLDatasetRow:
    """Construit une ligne ML neutre avec un horizon de six bougies."""
    return MLDatasetRow(
        observation_id=observation_id,
        job_id=job_id,
        symbol=symbol,
        timeframe="1h",
        decision_time=decision_time,
        source_open_time=decision_time - timedelta(hours=1),
        snapshot_status="confirmed",
        calculation_mode="canonical",
        source_algorithm_version="signal-evaluation-v3",
        source_dataset_version="binance-history-v1",
        profile_id="inline",
        profile_fingerprint="sha256:profile",
        horizon=6,
        entry_policy="signal_close",
        entry_time=decision_time,
        exit_time=decision_time + timedelta(hours=6),
        natr_percent=2.0,
        natr_multiplier=1.0,
        neutral_threshold_return=0.02,
        future_return=0.0,
        label=MarketDirectionLabel.NEUTRAL,
        features={
            "price.close": 100.0 + observation_id,
        },
    )


def hourly_rows(
    count: int,
    *,
    job_id: str = "job-1",
) -> tuple[MLDatasetRow, ...]:
    """Construit une série horaire continue."""
    return tuple(
        dataset_row(
            index + 1,
            decision_time=BASE_TIME + timedelta(hours=index),
            job_id=job_id,
        )
        for index in range(count)
    )


def test_split_purges_overlapping_future_targets() -> None:
    rows = hourly_rows(50)

    split = split_ml_dataset_chronologically(tuple(reversed(rows)))

    assert split.validation_start == (BASE_TIME + timedelta(hours=30))
    assert split.test_start == (BASE_TIME + timedelta(hours=40))

    assert len(split.train_rows) == 24
    assert len(split.validation_rows) == 4
    assert len(split.test_rows) == 10

    assert split.purged_before_validation == 6
    assert split.purged_before_test == 6

    assert split.source_row_count == 50
    assert split.retained_row_count == 38

    assert split.train_rows[0].observation_id == 1
    assert split.train_rows[-1].observation_id == 24

    assert split.validation_rows[0].observation_id == 31
    assert split.validation_rows[-1].observation_id == 34

    assert split.test_rows[0].observation_id == 41
    assert split.test_rows[-1].observation_id == 50

    assert split.train_rows[-1].exit_time < split.validation_start
    assert split.validation_rows[-1].exit_time < split.test_start


def test_split_uses_unique_decision_times_for_boundaries() -> None:
    rows: list[MLDatasetRow] = []
    observation_id = 1

    for hour in range(50):
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

    split = split_ml_dataset_chronologically(tuple(reversed(rows)))

    assert split.validation_start == (BASE_TIME + timedelta(hours=30))
    assert split.test_start == (BASE_TIME + timedelta(hours=40))

    assert len(split.train_rows) == 48
    assert len(split.validation_rows) == 8
    assert len(split.test_rows) == 20

    assert split.purged_before_validation == 12
    assert split.purged_before_test == 12

    train_times = {row.decision_time for row in split.train_rows}
    validation_times = {row.decision_time for row in split.validation_rows}
    test_times = {row.decision_time for row in split.test_rows}

    assert train_times.isdisjoint(validation_times)
    assert train_times.isdisjoint(test_times)
    assert validation_times.isdisjoint(test_times)

    assert {
        row.symbol for row in split.validation_rows if row.decision_time == split.validation_start
    } == {
        "BTC/USDC",
        "ETH/USDC",
    }


def test_split_supports_custom_ratios() -> None:
    rows = hourly_rows(100)

    split = split_ml_dataset_chronologically(
        rows,
        train_ratio=0.70,
        validation_ratio=0.15,
        test_ratio=0.15,
    )

    assert split.validation_start == (BASE_TIME + timedelta(hours=70))
    assert split.test_start == (BASE_TIME + timedelta(hours=85))

    assert len(split.train_rows) == 64
    assert len(split.validation_rows) == 9
    assert len(split.test_rows) == 15

    assert split.purged_before_validation == 6
    assert split.purged_before_test == 6


@pytest.mark.parametrize(
    (
        "train_ratio",
        "validation_ratio",
        "test_ratio",
    ),
    [
        (
            0.60,
            0.20,
            0.10,
        ),
        (
            0.0,
            0.50,
            0.50,
        ),
        (
            -0.10,
            0.50,
            0.60,
        ),
        (
            float("nan"),
            0.50,
            0.50,
        ),
        (
            float("inf"),
            0.25,
            0.25,
        ),
    ],
)
def test_split_rejects_invalid_ratios(
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> None:
    with pytest.raises(
        MLTemporalSplitError,
        match="proportions|égal à 1",
    ):
        split_ml_dataset_chronologically(
            hourly_rows(50),
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
        )


def test_split_rejects_duplicate_observations() -> None:
    first = dataset_row(
        1,
        decision_time=BASE_TIME,
    )
    duplicate = dataset_row(
        1,
        decision_time=BASE_TIME + timedelta(hours=1),
    )
    other = dataset_row(
        2,
        decision_time=BASE_TIME + timedelta(hours=2),
    )

    with pytest.raises(
        MLTemporalSplitError,
        match="plusieurs lignes",
    ):
        split_ml_dataset_chronologically(
            (
                first,
                duplicate,
                other,
            )
        )


def test_split_rejects_multiple_jobs() -> None:
    rows = list(hourly_rows(50))
    rows[-1] = dataset_row(
        rows[-1].observation_id,
        decision_time=rows[-1].decision_time,
        job_id="job-2",
    )

    with pytest.raises(
        MLTemporalSplitError,
        match="même job",
    ):
        split_ml_dataset_chronologically(tuple(rows))


def test_split_rejects_multiple_horizons() -> None:
    rows = list(hourly_rows(50))
    rows[-1] = rows[-1].model_copy(
        update={
            "horizon": 12,
        }
    )

    with pytest.raises(
        MLTemporalSplitError,
        match="même horizon",
    ):
        split_ml_dataset_chronologically(tuple(rows))


def test_split_rejects_too_few_rows() -> None:
    with pytest.raises(
        MLTemporalSplitError,
        match="au moins trois lignes",
    ):
        split_ml_dataset_chronologically(hourly_rows(2))


def test_split_rejects_too_few_distinct_times() -> None:
    rows = (
        dataset_row(
            1,
            decision_time=BASE_TIME,
        ),
        dataset_row(
            2,
            decision_time=BASE_TIME,
        ),
        dataset_row(
            3,
            decision_time=BASE_TIME,
        ),
    )

    with pytest.raises(
        MLTemporalSplitError,
        match="temps de décision distincts",
    ):
        split_ml_dataset_chronologically(rows)


def test_split_rejects_empty_train_after_purge() -> None:
    with pytest.raises(
        MLTemporalSplitError,
        match="entraînement est vide",
    ):
        split_ml_dataset_chronologically(hourly_rows(10))
