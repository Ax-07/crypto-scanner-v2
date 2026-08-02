"""Canaux de Donchian descriptifs et cassures causales."""

from __future__ import annotations

import math

import pandas as pd

from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorEvent,
    IndicatorSignal,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "build_donchian_signal",
    "calculate_donchian_channels",
    "detect_donchian_events",
]


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


def detect_donchian_events(
    data: dict[str, pd.Series] | None,
    close: pd.Series | None,
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les premières cassures du canal Donchian précédent.

    La borne de référence est calculée exclusivement avec les bougies
    terminées à t-1, afin d'éviter tout look-ahead.

    Une cassure n'est émise que lors de la première clôture hors du canal.
    Les bougies suivantes restant hors du canal ne génèrent pas de nouvel
    événement.
    """
    if data is None or close is None:
        return []

    required = {
        "previous_upper_channel",
        "previous_lower_channel",
    }
    if not required <= set(data):
        return []

    frame_columns = [
        close.astype(float).rename("close"),
        data["previous_upper_channel"].astype(float).rename(
            "previous_upper_channel"
        ),
        data["previous_lower_channel"].astype(float).rename(
            "previous_lower_channel"
        ),
    ]

    invalid_ohlc = data.get("_invalid_ohlc")
    if invalid_ohlc is not None:
        frame_columns.append(
            invalid_ohlc.astype(float).rename("_invalid_ohlc")
        )

    frame = pd.concat(frame_columns, axis=1).reset_index(drop=True)

    if len(frame) < 2:
        return []

    start_position = len(frame) - 1 if only_last else 1
    events: list[IndicatorEvent] = []

    for position in range(start_position, len(frame)):
        previous = frame.iloc[position - 1]
        current = frame.iloc[position]

        raw_values = (
            previous["close"],
            previous["previous_upper_channel"],
            previous["previous_lower_channel"],
            current["close"],
            current["previous_upper_channel"],
            current["previous_lower_channel"],
        )

        if any(pd.isna(value) for value in raw_values):
            continue

        previous_close = float(previous["close"])
        previous_upper = float(previous["previous_upper_channel"])
        previous_lower = float(previous["previous_lower_channel"])

        current_close = float(current["close"])
        current_upper = float(current["previous_upper_channel"])
        current_lower = float(current["previous_lower_channel"])

        numeric_values = (
            previous_close,
            previous_upper,
            previous_lower,
            current_close,
            current_upper,
            current_lower,
        )

        if not all(math.isfinite(value) for value in numeric_values):
            continue

        if current_close <= 0:
            continue

        if "_invalid_ohlc" in frame.columns:
            previous_invalid = bool(previous["_invalid_ohlc"])
            current_invalid = bool(current["_invalid_ohlc"])

            if previous_invalid or current_invalid:
                continue

        if current_upper < current_lower:
            continue

        currently_above = current_close > current_upper
        previously_above = previous_close > previous_upper

        currently_below = current_close < current_lower
        previously_below = previous_close < previous_lower

        if currently_above and not previously_above:
            distance = abs(current_close - current_upper) / current_close

            events.append(
                IndicatorEvent(
                    indicator="donchian",
                    position=position,
                    direction="bullish",
                    event="breakout_up",
                    kind="breakout",
                    strength=_clamp_strength(distance),
                    metadata={
                        "previous_close": previous_close,
                        "previous_reference": previous_upper,
                        "current_close": current_close,
                        "current_reference": current_upper,
                        "distance_percent": distance * 100.0,
                    },
                )
            )

        elif currently_below and not previously_below:
            distance = abs(current_close - current_lower) / current_close

            events.append(
                IndicatorEvent(
                    indicator="donchian",
                    position=position,
                    direction="bearish",
                    event="breakout_down",
                    kind="breakout",
                    strength=_clamp_strength(distance),
                    metadata={
                        "previous_close": previous_close,
                        "previous_reference": previous_lower,
                        "current_close": current_close,
                        "current_reference": current_lower,
                        "distance_percent": distance * 100.0,
                    },
                )
            )

    return events