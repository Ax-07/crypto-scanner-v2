from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.domain.indicators import (
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
    get_latest_rsi,
)


def series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


@pytest.mark.parametrize(
    ("values", "period", "expected"),
    [
        ([1, 2, 3], 3, None),
        ([1, 2, 3, 4], 3, 100.0),
        ([4, 3, 2, 1], 3, 0.0),
        ([5, 5, 5, 5], 3, 100.0),
        ([1, 2, 1, 2], 3, 77.7777777778),
        ([1, 3, 2], 2, 66.6666666667),
    ],
)
def test_rsi_known_series(values: list[float], period: int, expected: float | None) -> None:
    result = calculate_rsi(series(values), period)
    if expected is None:
        assert result.isna().all()
    else:
        assert result.iloc[-1] == pytest.approx(expected, abs=1e-9)


def test_rsi_nan_and_latest_value_are_characterized() -> None:
    values = series([1, 2, np.nan, 3, 4, 5])
    result = calculate_rsi(values, 2)
    assert result.iloc[:4].isna().all()
    assert result.iloc[-1] == pytest.approx(100)
    assert get_latest_rsi(series([1, 2]), 2) is None
    assert get_latest_rsi(series([1, 2, 3]), 2) == pytest.approx(100)


@pytest.mark.parametrize(
    ("calculator", "period", "expected"),
    [
        (calculate_sma, 3, [math.nan, math.nan, 2.0, 3.0]),
        (calculate_ema, 3, [math.nan, math.nan, 2.25, 3.125]),
        (calculate_sma, 2, [math.nan, 1.5, 2.5, 3.5]),
        (calculate_ema, 2, [math.nan, 1.6666666667, 2.5555555556, 3.5185185185]),
    ],
)
def test_moving_average_known_values(calculator, period: int, expected: list[float]) -> None:
    result = calculator(series([1, 2, 3, 4]), period)
    assert result.to_numpy() == pytest.approx(expected, nan_ok=True)


@pytest.mark.parametrize("calculator", [calculate_sma, calculate_ema])
def test_moving_average_insufficient_nan_and_constant(calculator) -> None:
    assert calculator(series([1, 2]), 3).isna().all()
    with_nan = calculator(series([1, np.nan, 3, 4]), 2)
    if calculator is calculate_sma:
        assert with_nan.iloc[:3].isna().all()
    else:
        assert with_nan.iloc[:2].isna().all()
        assert with_nan.iloc[2] == pytest.approx(2.7142857143)
    assert calculator(series([7, 7, 7, 7]), 3).dropna().tolist() == pytest.approx([7, 7])


def test_sma_and_ema_differ_on_non_constant_series() -> None:
    values = series([1, 2, 3, 10])
    assert calculate_sma(values, 3).iloc[-1] == pytest.approx(5)
    assert calculate_ema(values, 3).iloc[-1] == pytest.approx(6.125)


def test_macd_lines_histogram_warmup_and_custom_parameters() -> None:
    data = calculate_macd(series([1, 2, 3, 4, 5, 6]), 2, 3, 2)
    assert data["macd"].iloc[2:].to_numpy() == pytest.approx(
        [0.3055555556, 0.3935185185, 0.4436728395, 0.4708076132]
    )
    assert data["signal"].iloc[:3].isna().all()
    assert data["signal"].iloc[3:].to_numpy() == pytest.approx(
        [0.3641975309, 0.4171810699, 0.4529320988]
    )
    assert data["histogram"].iloc[3:].to_numpy() == pytest.approx(
        [0.0293209877, 0.0264917695, 0.0178755144]
    )
    assert pd.concat(calculate_macd(series([1, 2, 3]), 2, 3, 2), axis=1).dropna().empty


@pytest.mark.parametrize("value", [0.0, 5.0])
def test_macd_constant_series_is_zero(value: float) -> None:
    data = calculate_macd(series([value] * 8), 2, 3, 2)
    assert data["macd"].dropna().tolist() == pytest.approx([0] * 6)
    assert data["signal"].dropna().tolist() == pytest.approx([0] * 5)
    assert data["histogram"].dropna().tolist() == pytest.approx([0] * 5)


def test_macd_rising_and_falling_have_opposite_signs() -> None:
    rising = calculate_macd(series(list(range(1, 12))), 2, 4, 2)
    falling = calculate_macd(series(list(range(11, 0, -1))), 2, 4, 2)
    assert rising["macd"].dropna().iloc[-1] > 0
    assert falling["macd"].dropna().iloc[-1] < 0


def test_bollinger_known_values_population_std_and_custom_parameters() -> None:
    bands = calculate_bollinger_bands(series([1, 2, 3]), period=3, std_dev=2)
    population_std = math.sqrt(2 / 3)
    assert bands["middle"].iloc[-1] == pytest.approx(2)
    assert bands["upper"].iloc[-1] == pytest.approx(2 + 2 * population_std)
    assert bands["lower"].iloc[-1] == pytest.approx(2 - 2 * population_std)
    assert bands["middle"].iloc[:2].isna().all()
    custom = calculate_bollinger_bands(series([2, 4]), period=2, std_dev=1)
    assert custom["upper"].iloc[-1] == pytest.approx(4)
    assert custom["lower"].iloc[-1] == pytest.approx(2)


def test_bollinger_constant_and_nan_series() -> None:
    bands = calculate_bollinger_bands(series([5, 5, 5]), 3)
    assert [bands[key].iloc[-1] for key in ("upper", "middle", "lower")] == [5, 5, 5]
    assert calculate_bollinger_bands(series([1, np.nan, 3]), 3)["middle"].isna().all()


def test_stochastic_known_values_and_first_pair() -> None:
    data = calculate_stochastic(
        high=series([3, 4, 5, 6]),
        low=series([1, 2, 3, 4]),
        close=series([2, 3, 4, 5]),
        k_period=2,
        d_period=2,
    )
    assert data["k"].tolist() == pytest.approx(
        [math.nan, 2 / 3 * 100, 2 / 3 * 100, 2 / 3 * 100], nan_ok=True
    )
    assert data["d"].iloc[:2].isna().all()
    assert data["d"].iloc[2:].tolist() == pytest.approx([2 / 3 * 100] * 2)


def test_stochastic_zero_range_constant_and_insufficient() -> None:
    data = calculate_stochastic(series([5] * 4), series([5] * 4), series([5] * 4), 2, 2)
    assert data["k"].isna().all()
    assert data["d"].isna().all()
    short = calculate_stochastic(series([2]), series([0]), series([1]), 2, 2)
    assert short["k"].isna().all()
