"""Canaux de Keltner fondés sur l'EMA canonique et l'ATR de Wilder."""

from __future__ import annotations

import math

import pandas as pd

from app.domain.indicators.atr import calculate_atr
from app.domain.indicators.moving_averages import calculate_ema
from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorSignal,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = ["build_keltner_signal", "calculate_keltner_channels"]


def calculate_keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0,
    *,
    atr: pd.Series | None = None,
    middle_line: pd.Series | None = None,
) -> dict[str, pd.Series]:
    """Calcule Keltner en réutilisant, lorsqu'elles sont fournies, EMA et ATR."""
    if not isinstance(ema_period, int) or isinstance(ema_period, bool) or ema_period < 1:
        raise ValueError("ema_period doit être un entier positif")
    if not isinstance(atr_period, int) or isinstance(atr_period, bool) or atr_period < 1:
        raise ValueError("atr_period doit être un entier positif")
    if not math.isfinite(float(multiplier)) or multiplier <= 0:
        raise ValueError("multiplier doit être fini et strictement positif")
    middle = middle_line if middle_line is not None else calculate_ema(close, ema_period)
    atr_series = atr if atr is not None else calculate_atr(high, low, close, atr_period)["atr"]
    upper = middle + float(multiplier) * atr_series
    lower = middle - float(multiplier) * atr_series
    width = upper - lower
    width_percent = pd.Series(float("nan"), index=middle.index, dtype=float)
    valid_middle = middle.map(math.isfinite) & (middle > 0)
    width_percent.loc[valid_middle] = 100.0 * width.loc[valid_middle] / middle.loc[valid_middle]
    position = pd.Series(float("nan"), index=middle.index, dtype=float)
    positive_width = width.map(math.isfinite) & (width > 0)
    position.loc[positive_width] = (
        close.loc[positive_width].astype(float) - lower.loc[positive_width]
    ) / width.loc[positive_width]
    position.loc[width.map(math.isfinite) & (width.abs() <= 1e-12)] = 0.5
    frame = pd.concat(
        [
            high.astype(float).rename("high"),
            low.astype(float).rename("low"),
            close.astype(float).rename("close"),
        ],
        axis=1,
    )
    invalid_ohlc = (
        ~(
            frame.map(math.isfinite).all(axis=1)
            & (frame["high"] >= frame["low"])
            & (frame[["high", "low", "close"]] > 0).all(axis=1)
        )
    ).astype(float)
    return {
        "middle_line": middle,
        "upper_channel": upper,
        "lower_channel": lower,
        "atr": atr_series,
        "channel_width": width,
        "channel_width_percent": width_percent,
        "channel_position": position,
        "_invalid_ohlc": invalid_ohlc,
    }


def _component(value: float, unit: str) -> IndicatorComponent:
    return IndicatorComponent(
        value=value,
        normalized_value=value if unit == "ratio" else value / 100 if unit == "percent" else None,
        unit=unit,  # type: ignore[typeddict-item]
    )


def build_keltner_signal(
    data: dict[str, pd.Series],
    close: pd.Series,
) -> IndicatorSignal:
    """Détecte une sortie uniquement au franchissement de la bande précédente."""
    if close.empty:
        return _unavailable_signal("insufficient_data", "Historique Keltner insuffisant")
    names = (
        "middle_line",
        "upper_channel",
        "lower_channel",
        "atr",
        "channel_width",
        "channel_width_percent",
        "channel_position",
    )
    values = {name: float(data[name].iloc[-1]) for name in names}
    current_close = float(close.iloc[-1])
    if not math.isfinite(current_close) or current_close <= 0:
        return _unavailable_signal("invalid_data", "Close invalide pour Keltner")
    if bool(data.get("_invalid_ohlc", pd.Series([0.0])).iloc[-1]):
        return _unavailable_signal("invalid_data", "Données OHLC invalides pour Keltner")
    if not all(math.isfinite(value) for value in values.values()):
        return _unavailable_signal("insufficient_data", "Historique Keltner insuffisant")
    if (
        values["middle_line"] <= 0
        or values["lower_channel"] < 0
        or values["channel_width"] < 0
        or values["atr"] < 0
    ):
        return _unavailable_signal("invalid_data", "Canal Keltner invalide")

    state = (
        "above_channel"
        if current_close > values["upper_channel"]
        else "below_channel" if current_close < values["lower_channel"] else "inside_channel"
    )
    event: str | None = None
    distance_atr = 0.0
    if len(close) >= 2:
        previous_close = float(close.iloc[-2])
        previous_upper = float(data["upper_channel"].iloc[-2])
        previous_lower = float(data["lower_channel"].iloc[-2])
        if all(math.isfinite(value) for value in (previous_close, previous_upper, previous_lower)):
            if current_close > previous_upper and previous_close <= previous_upper:
                event = "breakout_up"
                distance_atr = (current_close - previous_upper) / max(values["atr"], 1e-12)
            elif current_close < previous_lower and previous_close >= previous_lower:
                event = "breakout_down"
                distance_atr = (previous_lower - current_close) / max(values["atr"], 1e-12)

    components = {
        "middle_line": _component(values["middle_line"], "price"),
        "upper_channel": _component(values["upper_channel"], "price"),
        "lower_channel": _component(values["lower_channel"], "price"),
        "atr": _component(values["atr"], "price"),
        "channel_width": _component(values["channel_width"], "price"),
        "channel_width_percent": _component(values["channel_width_percent"], "percent"),
        "channel_position": _component(values["channel_position"], "ratio"),
    }
    return IndicatorSignal(
        status="available",
        direction=(
            "bullish"
            if state == "above_channel"
            else "bearish" if state == "below_channel" else "neutral"
        ),
        signal=event,
        state=state,
        strength=_clamp_strength(distance_atr),
        reason=(
            "Cassure haussière du canal Keltner"
            if event == "breakout_up"
            else (
                "Cassure baissière du canal Keltner"
                if event == "breakout_down"
                else "Position courante dans le canal Keltner"
            )
        ),
        raw_value=values["channel_position"],
        components=components,
    )
