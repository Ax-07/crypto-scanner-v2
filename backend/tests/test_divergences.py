from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.services.market_stream import detect_divergences, find_pivots


@pytest.mark.parametrize(
    ("values", "pivot_type", "expected"),
    [
        ([3, 2, 1, 2, 3], "low", [2]),
        ([1, 2, 3, 2, 1], "high", [2]),
        ([3, 2, 1, 1, 3], "low", []),
        ([1, 2, 3, 3, 1], "high", []),
        ([3, 1, 3, 1, 3], "low", [1, 3]),
        ([1, 1, 1, 1, 1], "low", []),
        ([3, 2, np.nan, 2, 3], "low", []),
    ],
)
def test_find_pivots_strict_windows(values, pivot_type, expected) -> None:
    assert find_pivots(pd.Series(values), pivot_type, 1, 1) == expected


def test_find_pivots_custom_window_rejects_edges() -> None:
    values = pd.Series([9, 8, 7, 1, 7, 8, 9])
    assert find_pivots(values, "low", 3, 3) == [3]
    assert find_pivots(values.iloc[:-1], "low", 3, 3) == []


def divergence_case(kind: str, *, distance: int = 5) -> tuple[pd.DataFrame, pd.Series]:
    first = 3
    second = first + distance
    size = second + 4
    low = [20.0] * size
    high = [20.0] * size
    indicator = [50.0] * size
    if kind == "regular_bullish":
        low[first], low[second] = 10, 9
        indicator[first], indicator[second] = 40, 45
    elif kind == "hidden_bullish":
        low[first], low[second] = 10, 11
        indicator[first], indicator[second] = 45, 40
    elif kind == "regular_bearish":
        high[first], high[second] = 30, 31
        indicator[first], indicator[second] = 60, 55
    else:
        high[first], high[second] = 30, 29
        indicator[first], indicator[second] = 55, 60
    frame = pd.DataFrame(
        {
            "timestamp": [index * 1_000 for index in range(size)],
            "low": low,
            "high": high,
        }
    )
    return frame, pd.Series(indicator)


@pytest.mark.parametrize("source", ["RSI", "MACD"])
@pytest.mark.parametrize(
    "kind",
    ["regular_bullish", "hidden_bullish", "regular_bearish", "hidden_bearish"],
)
def test_all_four_divergence_types_and_complete_marker_fields(source: str, kind: str) -> None:
    frame, indicator = divergence_case(kind)
    markers = detect_divergences(frame, indicator, source, 2 if source == "RSI" else 0)
    assert len(markers) == 1
    marker = markers[0]
    assert marker["divergence_type"] == kind
    assert marker["source"] == source
    assert marker["category"] == "divergence"
    assert marker["time"] == 8
    assert marker["first_time"] == 3
    assert set(marker) == {
        "time",
        "position",
        "shape",
        "color",
        "text",
        "category",
        "source",
        "divergence_type",
        "first_time",
        "first_price",
        "second_price",
        "first_indicator",
        "second_indicator",
    }


@pytest.mark.parametrize(("distance", "detected"), [(4, False), (5, True), (60, True), (61, False)])
def test_divergence_minimum_and_maximum_distance(distance: int, detected: bool) -> None:
    frame, indicator = divergence_case("regular_bullish", distance=distance)
    assert bool(detect_divergences(frame, indicator, "RSI", 2)) is detected


def test_divergence_requires_price_and_indicator_movements_and_finite_pivots() -> None:
    frame, indicator = divergence_case("regular_bullish")
    weak_price = frame.copy()
    weak_price.loc[8, "low"] = 10
    assert detect_divergences(weak_price, indicator, "RSI", 2) == []
    weak_indicator = indicator.copy()
    weak_indicator.iloc[8] = 41
    assert detect_divergences(frame, weak_indicator, "RSI", 2) == []
    nan_indicator = indicator.copy()
    nan_indicator.iloc[8] = np.nan
    assert detect_divergences(frame, nan_indicator, "RSI", 2) == []


def test_hidden_divergences_can_be_disabled() -> None:
    frame, indicator = divergence_case("hidden_bullish")
    with patch("app.services.market_stream.INCLUDE_HIDDEN_DIVERGENCES", False):
        assert detect_divergences(frame, indicator, "RSI", 2) == []


def test_macd_zero_threshold_currently_accepts_indicator_equality() -> None:
    frame, indicator = divergence_case("regular_bullish")
    indicator.iloc[8] = indicator.iloc[3]
    marker = detect_divergences(frame, indicator, "MACD", 0)
    assert marker[0]["divergence_type"] == "regular_bullish"


def test_only_newly_confirmed_emits_exactly_at_right_delay() -> None:
    frame, indicator = divergence_case("regular_bullish")
    assert (
        detect_divergences(
            frame.iloc[:-1],
            indicator.iloc[:-1],
            "RSI",
            2,
            only_newly_confirmed=True,
        )
        == []
    )
    confirmed = detect_divergences(
        frame,
        indicator,
        "RSI",
        2,
        only_newly_confirmed=True,
    )
    assert len(confirmed) == 1
    old_frame = pd.concat(
        [frame, pd.DataFrame({"timestamp": [12_000], "low": [20], "high": [20]})],
        ignore_index=True,
    )
    old_indicator = pd.concat([indicator, pd.Series([50])], ignore_index=True)
    assert (
        detect_divergences(
            old_frame,
            old_indicator,
            "RSI",
            2,
            only_newly_confirmed=True,
        )
        == []
    )


def test_minimum_time_filters_marker_by_second_pivot_time() -> None:
    frame, indicator = divergence_case("regular_bearish")
    assert detect_divergences(frame, indicator, "RSI", 2, minimum_time=9) == []
    assert detect_divergences(frame, indicator, "RSI", 2, minimum_time=8)
