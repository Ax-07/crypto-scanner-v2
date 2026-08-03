from __future__ import annotations

import math

import pandas as pd
import pytest

from app.domain.indicators import (
    calculate_confluence_score,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_stochastic_signal,
    detect_trend,
)
from app.services.market_stream import build_indicator_event_markers


def paired(previous: tuple[float, float], current: tuple[float, float]):
    return {
        "macd": pd.Series([*previous[:1], *current[:1]]),
        "signal": pd.Series([previous[1], current[1]]),
    }


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ((0, 0), (1, 0), "bullish"),
        ((0, 0), (-1, 0), "bearish"),
        ((2, 1), (3, 1), "bullish"),
        ((-2, -1), (-3, -1), "bearish"),
        ((0, 0), (0, 0), "neutral"),
    ],
)
def test_macd_classification_crosses_and_maintains_state(previous, current, expected) -> None:
    assert detect_macd_signal(paired(previous, current)) == expected
    assert detect_macd_signal({"macd": pd.Series([1.0]), "signal": pd.Series([0.0])}) == "neutral"


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (-0.1, "oversold"),
        (0, "oversold"),
        (0.0001, "near_oversold"),
        (0.15, "near_oversold"),
        (0.1501, "neutral"),
        (0.8499, "neutral"),
        (0.85, "near_overbought"),
        (0.999, "near_overbought"),
        (1, "overbought"),
        (1.1, "overbought"),
    ],
)
def test_bollinger_classification_boundaries(position: float, expected: str) -> None:
    bands = {"lower": pd.Series([0.0]), "upper": pd.Series([100.0])}
    assert detect_bollinger_signal(pd.Series([position * 100]), bands) == expected


def test_constant_bollinger_width_is_neutral_degenerate() -> None:
    bands = {"lower": pd.Series([5.0]), "upper": pd.Series([5.0])}
    assert detect_bollinger_signal(pd.Series([5.0]), bands) == "neutral"


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ((10, 10), (15, 10), "bullish_cross"),
        ((90, 90), (85, 90), "bearish_cross"),
        ((10, 11), (20, 20), "oversold"),
        ((90, 89), (80, 80), "overbought"),
        ((10, 11), (20, 20.1), "neutral"),
        ((90, 89), (80, 79.9), "neutral"),
        ((10, 11), (19, 20), "oversold"),
        ((90, 89), (81, 80), "overbought"),
    ],
)
def test_stochastic_cross_priority_zones_and_boundaries(previous, current, expected) -> None:
    data = {"k": pd.Series([previous[0], current[0]]), "d": pd.Series([previous[1], current[1]])}
    assert detect_stochastic_signal(data) == expected


@pytest.mark.parametrize(
    ("price", "sma_fast", "sma_slow", "ema_fast", "ema_slow", "expected"),
    [
        (12, 11, 10, None, None, "bullish"),
        (8, 9, 10, None, None, "bearish"),
        (12, None, None, 11, 10, "bullish"),
        (8, None, None, 9, 10, "bearish"),
        (12, 11, 10, 11, 10, "bullish"),
        (8, 9, 10, 9, 10, "bearish"),
        (12, 11, 10, 9, 10, "neutral"),
        (12, 9, 10, 11, 10, "neutral"),
        (12, None, None, None, None, "unavailable"),
        (10, 9, None, None, None, "bullish"),
        (10, 10, None, None, None, "neutral"),
        (12, 10, 10, None, None, "neutral"),
    ],
)
def test_trend_current_permissive_vote_and_equalities(
    price, sma_fast, sma_slow, ema_fast, ema_slow, expected
) -> None:
    assert detect_trend(pd.Series([price]), sma_fast, sma_slow, ema_fast, ema_slow) == expected


def event_marker_bundle(
    ema_fast: list[float],
    ema_slow: list[float],
    macd: list[float],
    signal: list[float],
) -> dict[str, object]:
    """Construit un bundle minimal compatible avec les événements EMA/MACD."""
    macd_series = pd.Series(macd, dtype=float)
    signal_series = pd.Series(signal, dtype=float)

    return {
        "_ema_fast": pd.Series(ema_fast, dtype=float),
        "_ema_slow": pd.Series(ema_slow, dtype=float),
        "macd": {
            "macd": macd_series,
            "signal": signal_series,
            "histogram": macd_series - signal_series,
        },
    }


def test_indicator_event_markers_ema_macd_crosses_and_presentation() -> None:
    """Les événements métier EMA/MACD deviennent les marqueurs attendus."""
    frame = pd.DataFrame(
        {
            "timestamp": [1_000, 2_000, 3_000],
            "close": [100.0, 101.0, 102.0],
        }
    )

    markers = build_indicator_event_markers(
        frame,
        event_marker_bundle(
            ema_fast=[0.0, 1.0, 0.0],
            ema_slow=[0.0, 0.0, 1.0],
            macd=[0.0, 1.0, 1.0],
            signal=[0.0, 0.0, 0.5],
        ),
    )

    assert markers == [
        {
            "time": 2,
            "position": "belowBar",
            "shape": "arrowUp",
            "color": "#22c55e",
            "text": "EMA BUY",
            "category": "signal",
            "indicator": "ema",
        },
        {
            "time": 2,
            "position": "belowBar",
            "shape": "circle",
            "color": "#38bdf8",
            "text": "MACD haussier",
            "category": "signal",
            "indicator": "macd",
        },
        {
            "time": 3,
            "position": "aboveBar",
            "shape": "arrowDown",
            "color": "#ef4444",
            "text": "EMA SELL",
            "category": "signal",
            "indicator": "ema",
        },
    ]

    assert build_indicator_event_markers(frame.iloc[:1], {}) == []

    bearish_macd_markers = build_indicator_event_markers(
        frame,
        event_marker_bundle(
            ema_fast=[math.nan, math.nan, math.nan],
            ema_slow=[math.nan, math.nan, math.nan],
            macd=[1.0, 0.0, -1.0],
            signal=[0.0, 0.0, 0.0],
        ),
    )

    assert bearish_macd_markers[-1] == {
        "time": 3,
        "position": "aboveBar",
        "shape": "circle",
        "color": "#f59e0b",
        "text": "MACD baissier",
        "category": "signal",
        "indicator": "macd",
    }


def confluence(**changes):
    values = {
        "rsi_value": None,
        "rsi_threshold": 35,
        "trend_score": None,
        "max_trend_score": 0,
        "macd_signal": None,
        "bb_position": None,
        "stoch_signal": None,
        "weights": {},
    }
    values.update(changes)
    return calculate_confluence_score(**values)


@pytest.mark.parametrize(
    ("value", "factor"),
    [(30, 1), (30.0001, 0.75), (35, 0.75), (35.0001, 0.3), (49.9999, 0.3), (50, 0)],
)
def test_confluence_rsi_boundaries(value: float, factor: float) -> None:
    result = confluence(rsi_value=value, weights={"rsi": 1})
    assert result["score"] == pytest.approx(factor * 100)


@pytest.mark.parametrize(
    ("name", "value", "factor"),
    [
        ("macd_signal", "bullish", 1),
        ("macd_signal", "neutral", 0.4),
        ("macd_signal", "bearish", 0),
        ("macd_signal", "unknown", 0),
        ("bb_position", "oversold", 1),
        ("bb_position", "near_oversold", 0.75),
        ("bb_position", "neutral", 0.35),
        ("bb_position", "near_overbought", 0.1),
        ("bb_position", "overbought", 0),
        ("stoch_signal", "bullish_cross", 1),
        ("stoch_signal", "oversold", 0.9),
        ("stoch_signal", "neutral", 0.35),
        ("stoch_signal", "bearish_cross", 0.1),
        ("stoch_signal", "overbought", 0),
    ],
)
def test_confluence_each_class(name: str, value: str, factor: float) -> None:
    weight = {"bb_position": "bollinger", "stoch_signal": "stochastic"}.get(name, "macd")
    result = confluence(**{name: value}, weights={weight: 1})
    assert result["score"] == pytest.approx(factor * 100)


@pytest.mark.parametrize(
    ("score", "maximum", "expected"),
    [(0, 3, 0), (1, 3, 33.33), (3, 3, 100), (5, 3, 100), (-1, 3, 0)],
)
def test_confluence_trend_is_bounded(score: int, maximum: int, expected: float) -> None:
    assert (
        confluence(trend_score=score, max_trend_score=maximum, weights={"trend": 1})["score"]
        == expected
    )
    assert confluence(trend_score=1, max_trend_score=0, weights={"trend": 1}) is None


@pytest.mark.parametrize(
    ("value", "grade"),
    [
        (0, "F"),
        (49.99, "F"),
        (50, "D"),
        (59.99, "D"),
        (60, "C"),
        (69.99, "C"),
        (70, "B"),
        (79.99, "B"),
        (80, "A"),
        (89.99, "A"),
        (90, "A+"),
        (100, "A+"),
    ],
)
def test_confluence_grade_boundaries(value: float, grade: str) -> None:
    result = confluence(
        rsi_value=0,
        macd_signal="bearish",
        weights={"rsi": value, "macd": 100 - value},
    )
    assert result["score"] == value
    assert result["grade"] == grade
    assert sum(result["breakdown"].values()) == pytest.approx(value)
    assert sum(result["effective_weights"].values()) == pytest.approx(100)


def test_confluence_absent_zero_weights_rounding_and_renormalization() -> None:
    assert confluence(rsi_value=None, weights={"rsi": 1}) is None
    assert confluence(rsi_value=20, weights={"rsi": 0}) is None
    assert confluence(bb_position="unknown", weights={"bollinger": 1}) is None
    assert confluence(stoch_signal="unknown", weights={"stochastic": 1}) is None
    result = confluence(rsi_value=20, macd_signal="bearish", weights={"rsi": 1, "macd": 2})
    assert {key: result[key] for key in ("score", "grade", "breakdown", "effective_weights")} == {
        "score": 33.33,
        "grade": "F",
        "breakdown": {"rsi": 33.33, "macd": 0.0},
        "effective_weights": {"rsi": 33.33, "macd": 66.67},
    }


def test_confluence_five_factors_use_weighted_sum() -> None:
    result = confluence(
        rsi_value=20,
        trend_score=1,
        max_trend_score=2,
        macd_signal="neutral",
        bb_position="near_oversold",
        stoch_signal="overbought",
        weights={
            "rsi": 20,
            "trend": 25,
            "macd": 20,
            "bollinger": 20,
            "stochastic": 15,
        },
    )
    assert result["score"] == pytest.approx(55.5)
    assert sum(result["breakdown"].values()) == pytest.approx(55.5)
