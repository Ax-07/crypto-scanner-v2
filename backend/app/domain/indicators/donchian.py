"""Canaux de Donchian descriptifs et cassures causales."""

from __future__ import annotations

import math

import pandas as pd

from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorSignal,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = ["build_donchian_signal", "calculate_donchian_channels"]


def calculate_donchian_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> dict[str, pd.Series]:
    """Calcule le canal courant et le canal de référence terminé à ``t-1``."""
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise ValueError("period doit être un entier positif")
    frame = pd.concat(
        [
            high.astype(float).rename("high"),
            low.astype(float).rename("low"),
            close.astype(float).rename("close"),
        ],
        axis=1,
    )
    valid = (
        frame.map(math.isfinite).all(axis=1)
        & (frame["high"] >= frame["low"])
        & (frame[["high", "low", "close"]] > 0).all(axis=1)
    )
    invalid_ohlc = (~valid).rename("_invalid_ohlc")
    clean_high = frame["high"].where(valid)
    clean_low = frame["low"].where(valid)
    upper = clean_high.rolling(period, min_periods=period).max()
    lower = clean_low.rolling(period, min_periods=period).min()
    middle = (upper + lower) / 2.0
    width = upper - lower
    width_percent = pd.Series(float("nan"), index=frame.index, dtype=float)
    usable_middle = middle.map(math.isfinite) & (middle > 0)
    width_percent.loc[usable_middle] = 100.0 * width.loc[usable_middle] / middle.loc[usable_middle]
    position = pd.Series(float("nan"), index=frame.index, dtype=float)
    positive_width = width.map(math.isfinite) & (width > 0)
    position.loc[positive_width] = (
        frame.loc[positive_width, "close"] - lower.loc[positive_width]
    ) / width.loc[positive_width]
    position.loc[width.map(math.isfinite) & (width.abs() <= 1e-12)] = 0.5
    return {
        "upper_channel": upper,
        "middle_channel": middle,
        "lower_channel": lower,
        "previous_upper_channel": clean_high.shift(1).rolling(period, min_periods=period).max(),
        "previous_lower_channel": clean_low.shift(1).rolling(period, min_periods=period).min(),
        "channel_width": width,
        "channel_width_percent": width_percent,
        "channel_position": position,
        "_invalid_ohlc": invalid_ohlc.astype(float),
    }


def _component(value: float, unit: str) -> IndicatorComponent:
    normalized = value if unit == "ratio" else value / 100.0 if unit == "percent" else None
    return IndicatorComponent(
        value=value,
        normalized_value=normalized,
        unit=unit,  # type: ignore[typeddict-item]
    )


def build_donchian_signal(
    data: dict[str, pd.Series],
    close: pd.Series,
) -> IndicatorSignal:
    """Construit un événement strict contre le canal précédent, sans look-ahead."""
    if close.empty:
        return _unavailable_signal("insufficient_data", "Historique Donchian insuffisant")
    names = (
        "upper_channel",
        "middle_channel",
        "lower_channel",
        "previous_upper_channel",
        "previous_lower_channel",
        "channel_width",
        "channel_width_percent",
        "channel_position",
    )
    values = {name: float(data[name].iloc[-1]) for name in names}
    current_close = float(close.iloc[-1])
    if not math.isfinite(current_close) or current_close <= 0:
        return _unavailable_signal("invalid_data", "Close invalide pour Donchian")
    if bool(data.get("_invalid_ohlc", pd.Series([0.0])).iloc[-1]):
        return _unavailable_signal("invalid_data", "Données OHLC invalides pour Donchian")
    if not all(math.isfinite(value) for value in values.values()):
        return _unavailable_signal("insufficient_data", "Historique Donchian insuffisant")
    if values["channel_width"] < 0 or values["middle_channel"] <= 0:
        return _unavailable_signal("invalid_data", "Canal Donchian invalide")

    above = current_close > values["previous_upper_channel"]
    below = current_close < values["previous_lower_channel"]
    state = "above_channel" if above else "below_channel" if below else "inside_channel"
    event: str | None = None
    if above:
        event = "breakout_up"
    elif below:
        event = "breakout_down"
    if len(close) >= 2 and event is not None:
        previous_close = float(close.iloc[-2])
        previous_upper = float(data["previous_upper_channel"].iloc[-2])
        previous_lower = float(data["previous_lower_channel"].iloc[-2])
        if math.isfinite(previous_upper) and math.isfinite(previous_lower):
            previously_outside = (
                previous_close > previous_upper
                if event == "breakout_up"
                else previous_close < previous_lower
            )
            if previously_outside:
                event = None

    broken_band = (
        values["previous_upper_channel"]
        if state == "above_channel"
        else values["previous_lower_channel"]
    )
    distance = abs(current_close - broken_band) / current_close if state != "inside_channel" else 0
    components = {
        "upper_channel": _component(values["upper_channel"], "price"),
        "middle_channel": _component(values["middle_channel"], "price"),
        "lower_channel": _component(values["lower_channel"], "price"),
        "previous_upper_channel": _component(values["previous_upper_channel"], "price"),
        "previous_lower_channel": _component(values["previous_lower_channel"], "price"),
        "channel_width": _component(values["channel_width"], "price"),
        "channel_width_percent": _component(values["channel_width_percent"], "percent"),
        "channel_position": _component(values["channel_position"], "ratio"),
    }
    return IndicatorSignal(
        status="available",
        direction=(
            "bullish"
            if event == "breakout_up"
            else "bearish" if event == "breakout_down" else "neutral"
        ),
        signal=event,
        state=state,
        strength=_clamp_strength(distance),
        reason=(
            "Cassure haussière du canal Donchian"
            if event == "breakout_up"
            else (
                "Cassure baissière du canal Donchian"
                if event == "breakout_down"
                else "Prix à l'intérieur du canal Donchian"
            )
        ),
        raw_value=values["channel_position"],
        components=components,
    )
