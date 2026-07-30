"""Supertrend causal fondé sur l'ATR de Wilder."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.atr import calculate_atr
from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorSignal,
    SignalDirection,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = ["build_supertrend_signal", "calculate_supertrend"]


def calculate_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int = 10,
    multiplier: float = 3.0,
    *,
    atr: pd.Series | None = None,
) -> dict[str, pd.Series]:
    """Calcule les bandes finales et le régime Supertrend sans donnée future.

    À la première valeur ATR, le régime est initialisé d'après ``close >= hl2``.
    Les bandes finales suivent ensuite les règles utilisant seulement la bande
    et le close précédents.
    """
    if isinstance(atr_period, bool) or not isinstance(atr_period, int) or atr_period < 1:
        raise ValueError("atr_period doit être un entier supérieur ou égal à 1")
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("multiplier doit être fini et strictement positif")
    frame = pd.concat(
        [
            high.astype(float).rename("high"),
            low.astype(float).rename("low"),
            close.astype(float).rename("close"),
        ],
        axis=1,
    )
    atr_series = (
        atr.astype(float)
        if atr is not None
        else calculate_atr(frame["high"], frame["low"], frame["close"], atr_period)["atr"]
    )
    hl2 = (frame["high"] + frame["low"]) / 2.0
    basic_upper = hl2 + multiplier * atr_series
    basic_lower = hl2 - multiplier * atr_series
    upper = pd.Series(np.nan, index=frame.index, dtype=float, name="upper_band")
    lower = pd.Series(np.nan, index=frame.index, dtype=float, name="lower_band")
    trend = pd.Series(np.nan, index=frame.index, dtype=float, name="trend")
    line = pd.Series(np.nan, index=frame.index, dtype=float, name="supertrend")
    input_valid = pd.Series(False, index=frame.index, dtype=bool, name="input_valid")

    previous_index: object | None = None
    for index in frame.index:
        current_values = (
            float(frame.loc[index, "high"]),
            float(frame.loc[index, "low"]),
            float(frame.loc[index, "close"]),
            float(atr_series.loc[index]),
            float(basic_upper.loc[index]),
            float(basic_lower.loc[index]),
        )
        valid = (
            all(math.isfinite(value) for value in current_values)
            and current_values[0] >= current_values[1] > 0
            and current_values[2] > 0
        )
        if not valid:
            previous_index = None
            continue
        input_valid.loc[index] = True
        current_close = current_values[2]
        if previous_index is None:
            upper.loc[index] = current_values[4]
            lower.loc[index] = current_values[5]
            bullish = current_close >= float(hl2.loc[index])
        else:
            previous_close = float(frame.loc[previous_index, "close"])
            previous_upper = float(upper.loc[previous_index])
            previous_lower = float(lower.loc[previous_index])
            upper.loc[index] = (
                current_values[4]
                if current_values[4] < previous_upper or previous_close > previous_upper
                else previous_upper
            )
            lower.loc[index] = (
                current_values[5]
                if current_values[5] > previous_lower or previous_close < previous_lower
                else previous_lower
            )
            was_bullish = bool(trend.loc[previous_index] > 0)
            if was_bullish:
                bullish = not (current_close < float(lower.loc[index]))
            else:
                bullish = current_close > float(upper.loc[index])
        trend.loc[index] = 1.0 if bullish else -1.0
        line.loc[index] = float(lower.loc[index] if bullish else upper.loc[index])
        previous_index = index

    return {
        "supertrend": line,
        "upper_band": upper,
        "lower_band": lower,
        "atr": atr_series.rename("atr"),
        "trend": trend,
        "input_valid": input_valid,
    }


def _price_component(value: float) -> IndicatorComponent:
    return IndicatorComponent(value=value, normalized_value=None, unit="price")


def build_supertrend_signal(
    data: dict[str, pd.Series],
    close: pd.Series,
) -> IndicatorSignal:
    """Construit l'état persistant et n'émet un flip qu'au changement de régime."""
    if close.empty:
        return _unavailable_signal("insufficient_data", "Historique Supertrend insuffisant")
    current_close = float(close.iloc[-1])
    if not math.isfinite(current_close) or current_close <= 0:
        return _unavailable_signal("invalid_data", "Close invalide pour Supertrend")
    input_valid = data.get("input_valid")
    if input_valid is not None and (input_valid.empty or not bool(input_valid.iloc[-1])):
        return _unavailable_signal("invalid_data", "Données OHLC invalides pour Supertrend")
    current = {
        name: float(data[name].iloc[-1])
        for name in ("supertrend", "upper_band", "lower_band", "atr", "trend")
    }
    if not all(math.isfinite(value) for value in current.values()):
        return _unavailable_signal("insufficient_data", "Historique Supertrend insuffisant")
    if current["atr"] < 0:
        return _unavailable_signal("invalid_data", "ATR invalide pour Supertrend")

    bullish = current["trend"] > 0
    direction: SignalDirection = "bullish" if bullish else "bearish"
    state = "uptrend" if bullish else "downtrend"
    event: str | None = None
    previous_trends = data["trend"]
    if len(previous_trends) >= 2 and math.isfinite(float(previous_trends.iloc[-2])):
        previous_bullish = float(previous_trends.iloc[-2]) > 0
        if previous_bullish != bullish:
            event = "bullish_flip" if bullish else "bearish_flip"
    distance_ratio = (current_close - current["supertrend"]) / current_close
    distance_atr = abs(current_close - current["supertrend"]) / max(current["atr"], 1e-12)
    return IndicatorSignal(
        status="available",
        direction=direction,
        signal=event,
        state=state,
        strength=_clamp_strength(distance_atr),
        reason=f"Supertrend {state}",
        raw_value=current["supertrend"],
        components={
            "supertrend": _price_component(current["supertrend"]),
            "upper_band": _price_component(current["upper_band"]),
            "lower_band": _price_component(current["lower_band"]),
            "atr": _price_component(current["atr"]),
            "distance_ratio": IndicatorComponent(
                value=distance_ratio,
                normalized_value=distance_ratio,
                unit="ratio",
            ),
        },
    )
