"""Tests des signaux structurés (IndicatorSignal) de chaque indicateur.

Complète ``test_indicators_math.py`` (calculs purs) et
``test_signal_classification.py`` (classifications historiques) sans les
dupliquer: ce module se concentre sur le contrat commun ``IndicatorSignal``
et les nouvelles fonctions ``detect_*_signal``/``build_*_signal``.
"""

from __future__ import annotations
from typing import Literal
import math

import numpy as np
import pandas as pd
import pytest

from app.domain.indicators import (
    IndicatorSignal,
    build_bollinger_signal,
    build_macd_signal,
    build_stochastic_signal,
    calculate_bollinger_bands,
    calculate_macd,
    calculate_stochastic,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_moving_average_signal,
    detect_rsi_signal,
    detect_stochastic_signal,
)


def series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def assert_valid_contract(result: IndicatorSignal) -> None:
    """Vérifie que le résultat respecte le contrat commun IndicatorSignal."""
    required_keys = {
        "status",
        "direction",
        "signal",
        "state",
        "strength",
        "reason",
        "raw_value",
    }
    optional_keys = {"components"}

    assert required_keys <= set(result.keys())
    assert set(result.keys()) <= required_keys | optional_keys
    assert result["status"] in {"available", "insufficient_data", "invalid_data", "disabled"}
    assert result["direction"] in {"bullish", "bearish", "neutral"}
    assert 0.0 <= result["strength"] <= 1.0
    assert result["signal"] is None or isinstance(result["signal"], str)
    assert result["state"] is None or isinstance(result["state"], str)
    assert result["reason"] is None or isinstance(result["reason"], str)
    assert result["raw_value"] is None or isinstance(result["raw_value"], (int, float))

    components = result.get("components")

    if components is not None:
        assert isinstance(components, dict)

        for component in components.values():
            assert set(component) == {
                "value",
                "normalized_value",
                "unit",
            }
            assert component["value"] is None or isinstance(
                component["value"],
                (int, float),
            )
            assert component["normalized_value"] is None or isinstance(
                component["normalized_value"],
                (int, float),
            )


# --------------------------------------------------------------------------
# Contrat commun
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result",
    [
        detect_rsi_signal(series([50.0, 25.0])),
        detect_rsi_signal(None),
        detect_moving_average_signal(series([10.0]), series([9.0]), series([8.0]), family="sma"),
        detect_moving_average_signal(series([]), series([]), None, family="ema"),
        build_macd_signal({"macd": series([1.0, 2.0]), "signal": series([0.0, 1.0])}),
        build_macd_signal({"macd": series([]), "signal": series([])}),
        build_bollinger_signal(series([50.0]), {"upper": series([100.0]), "lower": series([0.0])}),
        build_bollinger_signal(series([]), {"upper": series([]), "lower": series([])}),
        build_stochastic_signal({"k": series([50.0, 60.0]), "d": series([40.0, 45.0])}),
        build_stochastic_signal({"k": series([]), "d": series([])}),
    ],
)
def test_indicator_signal_contract_is_respected(result: IndicatorSignal) -> None:
    assert_valid_contract(result)


def test_insufficient_and_invalid_data_are_neutral_with_zero_strength() -> None:
    insufficient = detect_rsi_signal(None)
    assert insufficient["status"] == "insufficient_data"
    assert insufficient["direction"] == "neutral"
    assert insufficient["strength"] == 0.0

    invalid = detect_rsi_signal(math.inf)
    assert invalid["status"] == "invalid_data"
    assert invalid["direction"] == "neutral"
    assert invalid["strength"] == 0.0


# --------------------------------------------------------------------------
# RSI
# --------------------------------------------------------------------------


def test_rsi_signal_oversold_and_overbought_extremes() -> None:
    oversold = detect_rsi_signal(20.0)
    assert oversold["state"] == "oversold"
    assert oversold["direction"] == "bullish"
    assert oversold["strength"] == pytest.approx(1.0)

    overbought = detect_rsi_signal(85.0)
    assert overbought["state"] == "overbought"
    assert overbought["direction"] == "bearish"
    assert overbought["strength"] == pytest.approx(1.0)


def test_rsi_signal_neutral_zone() -> None:
    result = detect_rsi_signal(50.0)
    assert result["state"] == "neutral"
    assert result["direction"] == "neutral"
    assert result["strength"] == pytest.approx(0.0)


def test_rsi_signal_exposes_normalized_components() -> None:
    result = detect_rsi_signal(60.0)

    components = result.get("components")

    assert components is not None

    assert components["rsi"]["value"] == pytest.approx(60.0)
    assert components["rsi"]["normalized_value"] == pytest.approx(0.6)
    assert components["rsi"]["unit"] == "index"

    assert components["previous_value"]["value"] is None
    assert components["previous_value"]["normalized_value"] is None

    assert components["change"]["value"] is None
    assert components["change"]["normalized_value"] is None

    assert components["distance_from_midpoint"]["value"] == pytest.approx(10.0)
    assert components["distance_from_midpoint"]["normalized_value"] == pytest.approx(0.1)

    assert components["distance_from_oversold"]["value"] == pytest.approx(30.0)
    assert components["distance_from_oversold"]["normalized_value"] == pytest.approx(0.3)

    assert components["distance_from_overbought"]["value"] == pytest.approx(-10.0)
    assert components["distance_from_overbought"]["normalized_value"] == pytest.approx(-0.1)


def test_rsi_signal_exposes_previous_value_and_change() -> None:
    result = detect_rsi_signal(series([25.0, 35.0]))

    components = result.get("components")

    assert components is not None
    assert result["signal"] == "exit_oversold"

    assert components["previous_value"]["value"] == pytest.approx(25.0)
    assert components["previous_value"]["normalized_value"] == pytest.approx(0.25)

    assert components["change"]["value"] == pytest.approx(10.0)
    assert components["change"]["normalized_value"] == pytest.approx(0.1)

    assert components["rsi"]["value"] == pytest.approx(35.0)
    assert components["rsi"]["normalized_value"] == pytest.approx(0.35)


def test_rsi_signal_ignores_non_finite_previous_component() -> None:
    result = detect_rsi_signal(series([math.inf, 50.0]))

    components = result.get("components")

    assert result["status"] == "available"
    assert components is not None
    assert components["previous_value"]["value"] is None
    assert components["change"]["value"] is None


def test_rsi_signal_exit_events_are_prioritized_over_state() -> None:
    exit_oversold = detect_rsi_signal(series([25.0, 35.0]))
    assert exit_oversold["signal"] == "exit_oversold"
    assert exit_oversold["direction"] == "bullish"
    assert exit_oversold["strength"] == pytest.approx(0.75)

    exit_overbought = detect_rsi_signal(series([75.0, 65.0]))
    assert exit_overbought["signal"] == "exit_overbought"
    assert exit_overbought["direction"] == "bearish"
    assert exit_overbought["strength"] == pytest.approx(0.75)


def test_rsi_signal_nan_is_insufficient() -> None:
    result = detect_rsi_signal(series([np.nan, np.nan]))
    assert result["status"] == "insufficient_data"


# --------------------------------------------------------------------------
# SMA / EMA
# --------------------------------------------------------------------------


@pytest.mark.parametrize("family", ["sma", "ema"])
def test_moving_average_bullish_and_bearish_cross(
    family: Literal["sma", "ema"],
) -> None:
    close = series([10, 11])
    bullish = detect_moving_average_signal(
        close, series([9.0, 11.0]), series([10.0, 10.0]), family=family
    )
    assert bullish["signal"] == "bullish_cross"
    assert bullish["direction"] == "bullish"

    bearish = detect_moving_average_signal(
        close, series([11.0, 9.0]), series([10.0, 10.0]), family=family
    )
    assert bearish["signal"] == "bearish_cross"
    assert bearish["direction"] == "bearish"


@pytest.mark.parametrize("family", ["sma", "ema"])
def test_moving_average_alignment_bullish_bearish_and_contradictory(
    family: Literal["sma", "ema"],
) -> None:
    bullish = detect_moving_average_signal(
        series([12.0]), series([11.0]), series([10.0]), family=family
    )
    assert bullish["signal"] == "bullish_alignment"

    bearish = detect_moving_average_signal(
        series([8.0]), series([9.0]), series([10.0]), family=family
    )
    assert bearish["signal"] == "bearish_alignment"

    contradictory = detect_moving_average_signal(
        series([12.0]), series([9.0]), series([10.0]), family=family
    )
    assert contradictory["signal"] == "neutral"
    assert contradictory["direction"] == "neutral"


def test_moving_average_price_comparison_without_slow_average() -> None:
    above = detect_moving_average_signal(series([12.0]), series([10.0]), None, family="ema")
    assert above["signal"] == "price_above"
    assert above["direction"] == "bullish"

    below = detect_moving_average_signal(series([8.0]), series([10.0]), None, family="sma")
    assert below["signal"] == "price_below"
    assert below["direction"] == "bearish"


def test_moving_average_insufficient_history() -> None:
    result = detect_moving_average_signal(series([]), series([]), series([]), family="sma")
    assert result["status"] == "insufficient_data"


def test_moving_average_non_finite_value_is_invalid_data() -> None:
    result = detect_moving_average_signal(
        series([1.0, 2.0]),
        series([1.0, math.inf]),
        None,
        family="sma",
    )

    assert result["status"] == "invalid_data"
    assert result["raw_value"] is None


# --------------------------------------------------------------------------
# MACD
# --------------------------------------------------------------------------


def test_macd_signal_bullish_and_bearish_cross() -> None:
    bullish = build_macd_signal({"macd": series([-1.0, 1.0]), "signal": series([0.0, 0.0])})
    assert bullish["signal"] == "bullish_cross"
    assert bullish["direction"] == "bullish"

    bearish = build_macd_signal({"macd": series([1.0, -1.0]), "signal": series([0.0, 0.0])})
    assert bearish["signal"] == "bearish_cross"
    assert bearish["direction"] == "bearish"


def test_macd_signal_persistent_states_above_and_below_signal_line() -> None:
    above = build_macd_signal({"macd": series([2.0, 2.0]), "signal": series([1.0, 1.0])})
    assert above["signal"] == "above_signal"
    assert above["direction"] == "bullish"

    below = build_macd_signal({"macd": series([1.0, 1.0]), "signal": series([2.0, 2.0])})
    assert below["signal"] == "below_signal"
    assert below["direction"] == "bearish"


def test_macd_signal_zero_position_encoded_in_state() -> None:
    above_zero = build_macd_signal({"macd": series([1.0, 1.0]), "signal": series([0.5, 0.5])})
    assert above_zero["state"] is not None and "above_zero" in above_zero["state"]

    below_zero = build_macd_signal({"macd": series([-1.0, -1.0]), "signal": series([-0.5, -0.5])})
    assert below_zero["state"] is not None and "below_zero" in below_zero["state"]


def test_macd_signal_exposes_continuous_components() -> None:
    result = build_macd_signal(
        {
            "macd": series([1.0, 2.0]),
            "signal": series([0.5, 1.0]),
        }
    )

    components = result.get("components")

    assert components is not None

    assert components["macd"]["value"] == pytest.approx(2.0)
    assert components["macd"]["normalized_value"] == pytest.approx(2 / 3)
    assert components["macd"]["unit"] == "price"

    assert components["signal_line"]["value"] == pytest.approx(1.0)
    assert components["signal_line"]["normalized_value"] == pytest.approx(1 / 3)

    assert components["histogram"]["value"] == pytest.approx(1.0)
    assert components["histogram"]["normalized_value"] == pytest.approx(1 / 3)

    assert components["relative_distance"]["value"] == pytest.approx(1 / 3)
    assert components["relative_distance"]["normalized_value"] == pytest.approx(1 / 3)

    assert components["previous_macd"]["value"] == pytest.approx(1.0)
    assert components["previous_signal_line"]["value"] == pytest.approx(0.5)
    assert components["previous_histogram"]["value"] == pytest.approx(0.5)

    assert components["macd_change"]["value"] == pytest.approx(1.0)
    assert components["macd_change"]["normalized_value"] == pytest.approx(1 / 3)

    assert components["signal_change"]["value"] == pytest.approx(0.5)
    assert components["signal_change"]["normalized_value"] == pytest.approx(1 / 3)

    assert components["histogram_change"]["value"] == pytest.approx(0.5)
    assert components["histogram_change"]["normalized_value"] == pytest.approx(1 / 3)


def test_macd_signal_components_accept_missing_previous_values() -> None:
    result = build_macd_signal(
        {
            "macd": series([2.0]),
            "signal": series([1.0]),
        }
    )

    components = result.get("components")

    assert result["status"] == "available"
    assert components is not None

    assert components["previous_macd"]["value"] is None
    assert components["previous_signal_line"]["value"] is None
    assert components["previous_histogram"]["value"] is None

    assert components["macd_change"]["value"] is None
    assert components["signal_change"]["value"] is None
    assert components["histogram_change"]["value"] is None


def test_detect_macd_signal_backward_compatibility() -> None:
    data = calculate_macd(series([1, 2, 3, 4, 5, 6]), 2, 3, 2)
    assert detect_macd_signal(data) in {"bullish", "bearish", "neutral"}


# --------------------------------------------------------------------------
# Bollinger
# --------------------------------------------------------------------------


def test_bollinger_signal_lower_band_breakout_and_reentry() -> None:
    breakout = build_bollinger_signal(
        series([50.0, -10.0]),
        {"upper": series([100.0, 100.0]), "lower": series([0.0, 0.0])},
    )
    assert breakout["signal"] == "lower_band_breakout"
    assert breakout["direction"] == "bearish"

    reentry = build_bollinger_signal(
        series([-10.0, 50.0]),
        {"upper": series([100.0, 100.0]), "lower": series([0.0, 0.0])},
    )
    assert reentry["signal"] == "lower_band_reentry"
    assert reentry["direction"] == "bullish"


def test_bollinger_signal_upper_band_breakout_and_reentry() -> None:
    breakout = build_bollinger_signal(
        series([50.0, 110.0]),
        {"upper": series([100.0, 100.0]), "lower": series([0.0, 0.0])},
    )
    assert breakout["signal"] == "upper_band_breakout"
    assert breakout["direction"] == "bullish"

    reentry = build_bollinger_signal(
        series([110.0, 50.0]),
        {"upper": series([100.0, 100.0]), "lower": series([0.0, 0.0])},
    )
    assert reentry["signal"] == "upper_band_reentry"
    assert reentry["direction"] == "bearish"


def test_bollinger_signal_neutral_position() -> None:
    result = build_bollinger_signal(
        series([50.0]), {"upper": series([100.0]), "lower": series([0.0])}
    )
    assert result["state"] == "neutral"
    assert result["direction"] == "neutral"


def test_bollinger_signal_exposes_continuous_components() -> None:
    result = build_bollinger_signal(
        series([100.0, 110.0]),
        {
            "upper": series([110.0, 120.0]),
            "middle": series([100.0, 105.0]),
            "lower": series([90.0, 90.0]),
        },
    )

    components = result.get("components")

    assert result["status"] == "available"
    assert result["signal"] == "neutral"
    assert components is not None

    assert components["middle_band"]["value"] == pytest.approx(105.0)
    assert components["middle_band"]["normalized_value"] == pytest.approx(105 / 110)

    assert components["upper_band"]["value"] == pytest.approx(120.0)
    assert components["upper_band"]["normalized_value"] == pytest.approx(120 / 110)

    assert components["lower_band"]["value"] == pytest.approx(90.0)
    assert components["lower_band"]["normalized_value"] == pytest.approx(90 / 110)

    assert components["band_width"]["value"] == pytest.approx(30.0)
    assert components["band_width"]["normalized_value"] == pytest.approx(30 / 110)

    assert components["band_width_percent"]["value"] == pytest.approx(100 * 30 / 105)
    assert components["band_width_percent"]["normalized_value"] == pytest.approx(30 / 105)

    assert components["band_position"]["value"] == pytest.approx(20 / 30)
    assert components["band_position"]["normalized_value"] == pytest.approx(20 / 30)

    assert components["price_to_middle_distance"]["value"] == pytest.approx(5.0)
    assert components["price_to_middle_distance"]["normalized_value"] == pytest.approx(5 / 215)

    assert components["price_to_upper_distance"]["value"] == pytest.approx(-10.0)
    assert components["price_to_upper_distance"]["normalized_value"] == pytest.approx(-10 / 230)

    assert components["price_to_lower_distance"]["value"] == pytest.approx(20.0)
    assert components["price_to_lower_distance"]["normalized_value"] == pytest.approx(20 / 200)

    assert components["previous_band_width_percent"]["value"] == pytest.approx(20.0)
    assert components["previous_band_position"]["value"] == pytest.approx(0.5)

    assert components["band_width_percent_change"]["value"] == pytest.approx((100 * 30 / 105) - 20)
    assert components["band_position_change"]["value"] == pytest.approx((20 / 30) - 0.5)

    assert components["middle_band_change"]["value"] == pytest.approx(5.0)
    assert components["middle_band_change"]["normalized_value"] == pytest.approx(5 / 205)


def test_bollinger_components_accept_missing_previous_values() -> None:
    result = build_bollinger_signal(
        series([100.0]),
        {
            "upper": series([110.0]),
            "middle": series([100.0]),
            "lower": series([90.0]),
        },
    )

    components = result.get("components")

    assert result["status"] == "available"
    assert components is not None

    assert components["previous_band_width_percent"]["value"] is None
    assert components["previous_band_position"]["value"] is None
    assert components["band_width_percent_change"]["value"] is None
    assert components["band_position_change"]["value"] is None
    assert components["middle_band_change"]["value"] is None


def test_bollinger_signal_degenerate_band_is_invalid_data_and_zero_strength() -> None:
    result = build_bollinger_signal(series([5.0]), {"upper": series([5.0]), "lower": series([5.0])})
    assert result["status"] == "invalid_data"
    assert result["strength"] == 0.0
    assert result["direction"] == "neutral"


def test_bollinger_non_finite_value_is_invalid_data() -> None:
    result = build_bollinger_signal(
        series([1.0, math.inf]),
        {
            "upper": series([2.0, math.inf]),
            "lower": series([0.0, 0.0]),
        },
    )

    assert result["status"] == "invalid_data"
    assert result["raw_value"] is None


def test_detect_bollinger_signal_backward_compatibility() -> None:
    bands = calculate_bollinger_bands(series([1, 2, 3, 4, 5]), period=3, std_dev=2)
    assert detect_bollinger_signal(series([1, 2, 3, 4, 5]), bands) in {
        "oversold",
        "near_oversold",
        "neutral",
        "near_overbought",
        "overbought",
    }


# --------------------------------------------------------------------------
# Stochastique
# --------------------------------------------------------------------------


def test_stochastic_signal_bullish_cross_in_and_out_of_oversold() -> None:
    in_oversold = build_stochastic_signal({"k": series([10.0, 15.0]), "d": series([11.0, 10.0])})
    assert in_oversold["signal"] == "bullish_cross"
    assert in_oversold["state"] == "oversold"
    assert in_oversold["strength"] == pytest.approx(1.0)

    out_of_oversold = build_stochastic_signal(
        {"k": series([40.0, 55.0]), "d": series([50.0, 50.0])}
    )
    assert out_of_oversold["signal"] == "bullish_cross"
    assert out_of_oversold["state"] == "neutral"
    assert out_of_oversold["strength"] == pytest.approx(0.6)


def test_stochastic_signal_bearish_cross_in_and_out_of_overbought() -> None:
    in_overbought = build_stochastic_signal({"k": series([90.0, 85.0]), "d": series([89.0, 90.0])})
    assert in_overbought["signal"] == "bearish_cross"
    assert in_overbought["state"] == "overbought"
    assert in_overbought["strength"] == pytest.approx(1.0)

    out_of_overbought = build_stochastic_signal(
        {"k": series([60.0, 45.0]), "d": series([50.0, 50.0])}
    )
    assert out_of_overbought["signal"] == "bearish_cross"
    assert out_of_overbought["state"] == "neutral"
    assert out_of_overbought["strength"] == pytest.approx(0.6)


def test_stochastic_signal_extreme_states_without_cross() -> None:
    oversold = build_stochastic_signal({"k": series([10.0, 11.0]), "d": series([12.0, 13.0])})
    assert oversold["signal"] == "oversold"
    assert oversold["direction"] == "bullish"

    overbought = build_stochastic_signal({"k": series([90.0, 89.0]), "d": series([88.0, 87.0])})
    assert overbought["signal"] == "overbought"
    assert overbought["direction"] == "bearish"


def test_detect_stochastic_signal_backward_compatibility() -> None:
    data = calculate_stochastic(
        high=series([3, 4, 5, 6]),
        low=series([1, 2, 3, 4]),
        close=series([2, 3, 4, 5]),
        k_period=2,
        d_period=2,
    )
    assert detect_stochastic_signal(data) in {
        "bullish_cross",
        "oversold",
        "neutral",
        "bearish_cross",
        "overbought",
    }


def test_stochastic_signal_exposes_continuous_components() -> None:
    result = build_stochastic_signal(
        {
            "k": series([10.0, 30.0]),
            "d": series([20.0, 25.0]),
        }
    )

    components = result.get("components")

    assert components is not None
    assert result["signal"] == "bullish_cross"

    assert components["k"]["value"] == pytest.approx(30.0)
    assert components["k"]["normalized_value"] == pytest.approx(0.3)
    assert components["k"]["unit"] == "index"

    assert components["d"]["value"] == pytest.approx(25.0)
    assert components["d"]["normalized_value"] == pytest.approx(0.25)

    assert components["spread"]["value"] == pytest.approx(5.0)
    assert components["spread"]["normalized_value"] == pytest.approx(0.05)

    assert components["previous_k"]["value"] == pytest.approx(10.0)
    assert components["previous_k"]["normalized_value"] == pytest.approx(0.1)

    assert components["previous_d"]["value"] == pytest.approx(20.0)
    assert components["previous_d"]["normalized_value"] == pytest.approx(0.2)

    assert components["previous_spread"]["value"] == pytest.approx(-10.0)
    assert components["previous_spread"]["normalized_value"] == pytest.approx(-0.1)

    assert components["k_change"]["value"] == pytest.approx(20.0)
    assert components["k_change"]["normalized_value"] == pytest.approx(0.2)

    assert components["d_change"]["value"] == pytest.approx(5.0)
    assert components["d_change"]["normalized_value"] == pytest.approx(0.05)

    assert components["spread_change"]["value"] == pytest.approx(15.0)
    assert components["spread_change"]["normalized_value"] == pytest.approx(0.15)


def test_stochastic_signal_components_accept_missing_previous_values() -> None:
    result = build_stochastic_signal(
        {
            "k": series([40.0]),
            "d": series([45.0]),
        }
    )

    components = result.get("components")

    assert result["status"] == "available"
    assert components is not None

    assert components["k"]["value"] == pytest.approx(40.0)
    assert components["d"]["value"] == pytest.approx(45.0)
    assert components["spread"]["value"] == pytest.approx(-5.0)

    assert components["previous_k"]["value"] is None
    assert components["previous_d"]["value"] is None
    assert components["previous_spread"]["value"] is None

    assert components["k_change"]["value"] is None
    assert components["d_change"]["value"] is None
    assert components["spread_change"]["value"] is None
