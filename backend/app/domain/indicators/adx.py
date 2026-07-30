"""Directional Movement Index, DX, ADX et signal structuré."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorSignal,
    SignalDirection,
    _clamp_strength,
    _unavailable_signal,
)
from app.domain.indicators.wilder import (
    calculate_directional_movement,
    calculate_true_range,
    wilder_smoothing,
)

__all__ = ["build_adx_signal", "calculate_adx_dmi"]


def calculate_adx_dmi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    *,
    true_range: pd.Series | None = None,
) -> dict[str, pd.Series]:
    """Calcule +DI, -DI, DX et ADX selon les amorçages de Wilder.

    +DM/-DM commencent à zéro sur la première bougie. Les premiers DMI sont
    disponibles à l'index ``period - 1`` et le premier ADX à
    ``2 * period - 2`` (27 bougies pour une période 14).
    """
    tr = true_range if true_range is not None else calculate_true_range(high, low, close)
    movement = calculate_directional_movement(high, low)
    smoothed_tr = wilder_smoothing(tr, period)
    smoothed_plus = wilder_smoothing(movement["plus_dm"], period)
    smoothed_minus = wilder_smoothing(movement["minus_dm"], period)

    plus_di = pd.Series(np.nan, index=tr.index, dtype=float, name="plus_di")
    minus_di = pd.Series(np.nan, index=tr.index, dtype=float, name="minus_di")
    ready = smoothed_tr.notna() & smoothed_plus.notna() & smoothed_minus.notna()
    positive = ready & (smoothed_tr > 0)
    zero = ready & (smoothed_tr == 0)
    plus_di.loc[positive] = 100.0 * smoothed_plus.loc[positive] / smoothed_tr.loc[positive]
    minus_di.loc[positive] = 100.0 * smoothed_minus.loc[positive] / smoothed_tr.loc[positive]
    plus_di.loc[zero] = 0.0
    minus_di.loc[zero] = 0.0

    dx = pd.Series(np.nan, index=tr.index, dtype=float, name="dx")
    denominator = plus_di + minus_di
    di_ready = plus_di.notna() & minus_di.notna()
    dx.loc[di_ready & (denominator == 0)] = 0.0
    nonzero = di_ready & (denominator > 0)
    dx.loc[nonzero] = (
        100.0 * (plus_di.loc[nonzero] - minus_di.loc[nonzero]).abs() / denominator.loc[nonzero]
    )
    adx = wilder_smoothing(dx, period).rename("adx")
    return {
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "dx": dx,
        "true_range": tr,
    }


def _adx_state(value: float, weak_threshold: float, strong_threshold: float) -> str:
    if value < weak_threshold:
        return "weak_trend"
    if value < strong_threshold:
        return "developing_trend"
    return "strong_trend"


def _component(value: float) -> IndicatorComponent:
    return IndicatorComponent(
        value=value,
        normalized_value=value / 100.0,
        unit="index",
    )


def build_adx_signal(
    data: dict[str, pd.Series],
    *,
    weak_threshold: float = 20,
    strong_threshold: float = 25,
) -> IndicatorSignal:
    """Construit le signal ADX/DMI ; les croisements ont priorité."""
    if not (
        math.isfinite(weak_threshold)
        and math.isfinite(strong_threshold)
        and 0 <= weak_threshold < strong_threshold <= 100
    ):
        return _unavailable_signal("invalid_data", "Seuils ADX invalides")
    frame = pd.concat(
        [
            data["adx"].rename("adx"),
            data["plus_di"].rename("plus_di"),
            data["minus_di"].rename("minus_di"),
            data["dx"].rename("dx"),
        ],
        axis=1,
    )
    if frame.empty:
        return _unavailable_signal("insufficient_data", "Historique ADX insuffisant")
    true_range = data.get("true_range")
    if true_range is not None and (
        true_range.empty or not math.isfinite(float(true_range.iloc[-1]))
    ):
        return _unavailable_signal("invalid_data", "Données OHLC invalides pour l'ADX")
    current = frame.iloc[-1]
    values = tuple(float(current[name]) for name in ("adx", "plus_di", "minus_di", "dx"))
    if not all(math.isfinite(value) for value in values):
        return _unavailable_signal("insufficient_data", "Historique ADX insuffisant")
    adx, plus_di, minus_di, dx = values
    direction: SignalDirection = (
        "bullish" if plus_di > minus_di else "bearish" if minus_di > plus_di else "neutral"
    )
    state = _adx_state(adx, weak_threshold, strong_threshold)

    event: str | None = None
    if len(frame) >= 2 and frame.iloc[-2].notna().all():
        previous = frame.iloc[-2]
        previous_plus = float(previous["plus_di"])
        previous_minus = float(previous["minus_di"])
        previous_state = _adx_state(float(previous["adx"]), weak_threshold, strong_threshold)
        if previous_plus <= previous_minus and plus_di > minus_di:
            event = "bullish_cross"
        elif previous_plus >= previous_minus and minus_di > plus_di:
            event = "bearish_cross"
        elif previous_state != "strong_trend" and state == "strong_trend":
            event = "trend_strengthening"
        elif previous_state == "strong_trend" and state != "strong_trend":
            event = "trend_weakening"

    return IndicatorSignal(
        status="available",
        direction=direction,
        signal=event,
        state=state,
        strength=_clamp_strength(adx / 50.0),
        reason=f"ADX {state}, +DI {plus_di:.2f}, -DI {minus_di:.2f}",
        raw_value=adx,
        components={
            "adx": _component(adx),
            "plus_di": _component(plus_di),
            "minus_di": _component(minus_di),
            "dx": _component(dx),
        },
    )
