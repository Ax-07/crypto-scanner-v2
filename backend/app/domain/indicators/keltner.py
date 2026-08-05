"""Canaux de Keltner fondés sur l'EMA canonique et l'ATR de Wilder."""

from __future__ import annotations

import math

import pandas as pd

from app.domain.indicators.atr import calculate_atr
from app.domain.indicators.moving_averages import calculate_ema
from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorComponentUnit,
    IndicatorEvent,
    IndicatorSignal,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "build_keltner_signal",
    "calculate_keltner_channels",
    "detect_keltner_events",
]


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


def _component(
    value: float | None,
    unit: IndicatorComponentUnit,
    *,
    normalized_value: float | None = None,
) -> IndicatorComponent:
    """Construit une composante Keltner éventuellement indisponible."""
    if value is None:
        return IndicatorComponent(
            value=None,
            normalized_value=None,
            unit=unit,
        )

    normalized = normalized_value

    if normalized is None:
        if unit == "ratio":
            normalized = value
        elif unit == "percent":
            normalized = value / 100.0

    return IndicatorComponent(
        value=value,
        normalized_value=normalized,
        unit=unit,
    )


def _finite_value(
    values: pd.Series,
    position: int,
) -> float | None:
    """Retourne une valeur finie d'une série lorsqu'elle existe."""
    try:
        value = float(values.iloc[position])
    except (IndexError, TypeError, ValueError):
        return None

    return value if math.isfinite(value) else None


def _normalized_price(
    value: float | None,
    close_value: float | None,
) -> float | None:
    """Normalise une valeur exprimée en prix par la clôture."""
    if value is None or close_value is None or close_value <= 0:
        return None

    return value / close_value


def _difference(
    current: float,
    previous: float | None,
) -> float | None:
    """Retourne une différence causale lorsque la référence existe."""
    if previous is None:
        return None

    return current - previous


def _relative_change(
    current: float,
    previous: float,
) -> float:
    """Normalise une variation signée entre deux valeurs."""
    denominator = abs(current) + abs(previous)

    if denominator <= 1e-12:
        return 0.0

    return (current - previous) / denominator


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

    previous_close_value = _finite_value(
        close,
        -2,
    )
    if previous_close_value is not None and previous_close_value <= 0:
        previous_close_value = None

    previous_middle = _finite_value(
        data["middle_line"],
        -2,
    )
    previous_upper_value = _finite_value(
        data["upper_channel"],
        -2,
    )
    previous_lower_value = _finite_value(
        data["lower_channel"],
        -2,
    )
    previous_atr = _finite_value(
        data["atr"],
        -2,
    )
    previous_width = _finite_value(
        data["channel_width"],
        -2,
    )
    previous_width_percent = _finite_value(
        data["channel_width_percent"],
        -2,
    )
    previous_position = _finite_value(
        data["channel_position"],
        -2,
    )

    price_to_middle = current_close - values["middle_line"]
    price_to_upper = current_close - values["upper_channel"]
    price_to_lower = current_close - values["lower_channel"]

    price_to_previous_upper = _difference(
        current_close,
        previous_upper_value,
    )
    price_to_previous_lower = _difference(
        current_close,
        previous_lower_value,
    )

    atr_denominator = max(
        values["atr"],
        1e-12,
    )

    middle_line_change = _difference(
        values["middle_line"],
        previous_middle,
    )
    upper_channel_change = _difference(
        values["upper_channel"],
        previous_upper_value,
    )
    lower_channel_change = _difference(
        values["lower_channel"],
        previous_lower_value,
    )
    atr_change = _difference(
        values["atr"],
        previous_atr,
    )
    channel_width_change = _difference(
        values["channel_width"],
        previous_width,
    )
    channel_width_percent_change = _difference(
        values["channel_width_percent"],
        previous_width_percent,
    )
    channel_position_change = _difference(
        values["channel_position"],
        previous_position,
    )

    components = {
        "middle_line": _component(
            values["middle_line"],
            "price",
            normalized_value=(values["middle_line"] / current_close),
        ),
        "upper_channel": _component(
            values["upper_channel"],
            "price",
            normalized_value=(values["upper_channel"] / current_close),
        ),
        "lower_channel": _component(
            values["lower_channel"],
            "price",
            normalized_value=(values["lower_channel"] / current_close),
        ),
        "atr": _component(
            values["atr"],
            "price",
            normalized_value=(values["atr"] / current_close),
        ),
        "channel_width": _component(
            values["channel_width"],
            "price",
            normalized_value=(values["channel_width"] / current_close),
        ),
        "channel_width_percent": _component(
            values["channel_width_percent"],
            "percent",
        ),
        "channel_position": _component(
            values["channel_position"],
            "ratio",
        ),
        "price_to_middle_distance": _component(
            price_to_middle,
            "price",
            normalized_value=(price_to_middle / current_close),
        ),
        "price_to_upper_distance": _component(
            price_to_upper,
            "price",
            normalized_value=(price_to_upper / current_close),
        ),
        "price_to_lower_distance": _component(
            price_to_lower,
            "price",
            normalized_value=(price_to_lower / current_close),
        ),
        "price_to_previous_upper_distance": _component(
            price_to_previous_upper,
            "price",
            normalized_value=_normalized_price(
                price_to_previous_upper,
                current_close,
            ),
        ),
        "price_to_previous_lower_distance": _component(
            price_to_previous_lower,
            "price",
            normalized_value=_normalized_price(
                price_to_previous_lower,
                current_close,
            ),
        ),
        "price_to_middle_atr": _component(
            price_to_middle / atr_denominator,
            "ratio",
        ),
        "price_to_upper_atr": _component(
            price_to_upper / atr_denominator,
            "ratio",
        ),
        "price_to_lower_atr": _component(
            price_to_lower / atr_denominator,
            "ratio",
        ),
        "price_to_previous_upper_atr": _component(
            (
                price_to_previous_upper / atr_denominator
                if price_to_previous_upper is not None
                else None
            ),
            "ratio",
        ),
        "price_to_previous_lower_atr": _component(
            (
                price_to_previous_lower / atr_denominator
                if price_to_previous_lower is not None
                else None
            ),
            "ratio",
        ),
        "previous_middle_line": _component(
            previous_middle,
            "price",
            normalized_value=_normalized_price(
                previous_middle,
                previous_close_value,
            ),
        ),
        "previous_upper_channel": _component(
            previous_upper_value,
            "price",
            normalized_value=_normalized_price(
                previous_upper_value,
                previous_close_value,
            ),
        ),
        "previous_lower_channel": _component(
            previous_lower_value,
            "price",
            normalized_value=_normalized_price(
                previous_lower_value,
                previous_close_value,
            ),
        ),
        "previous_atr": _component(
            previous_atr,
            "price",
            normalized_value=_normalized_price(
                previous_atr,
                previous_close_value,
            ),
        ),
        "previous_channel_width": _component(
            previous_width,
            "price",
            normalized_value=_normalized_price(
                previous_width,
                previous_close_value,
            ),
        ),
        "previous_channel_width_percent": _component(
            previous_width_percent,
            "percent",
        ),
        "previous_channel_position": _component(
            previous_position,
            "ratio",
        ),
        "middle_line_change": _component(
            middle_line_change,
            "price",
            normalized_value=(
                _relative_change(
                    values["middle_line"],
                    previous_middle,
                )
                if previous_middle is not None
                else None
            ),
        ),
        "upper_channel_change": _component(
            upper_channel_change,
            "price",
            normalized_value=(
                _relative_change(
                    values["upper_channel"],
                    previous_upper_value,
                )
                if previous_upper_value is not None
                else None
            ),
        ),
        "lower_channel_change": _component(
            lower_channel_change,
            "price",
            normalized_value=(
                _relative_change(
                    values["lower_channel"],
                    previous_lower_value,
                )
                if previous_lower_value is not None
                else None
            ),
        ),
        "atr_change": _component(
            atr_change,
            "price",
            normalized_value=(
                _relative_change(
                    values["atr"],
                    previous_atr,
                )
                if previous_atr is not None
                else None
            ),
        ),
        "channel_width_change": _component(
            channel_width_change,
            "price",
            normalized_value=(
                _relative_change(
                    values["channel_width"],
                    previous_width,
                )
                if previous_width is not None
                else None
            ),
        ),
        "channel_width_percent_change": _component(
            channel_width_percent_change,
            "percent",
        ),
        "channel_position_change": _component(
            channel_position_change,
            "ratio",
        ),
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


def detect_keltner_events(
    data: dict[str, pd.Series] | None,
    close: pd.Series | None,
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les premières cassures des bandes Keltner précédentes.

    Une cassure haussière est produite lorsque la clôture courante dépasse
    la bande haute calculée sur la bougie précédente, alors que la clôture
    précédente ne dépassait pas cette même bande.

    Une cassure baissière applique la règle symétrique avec la bande basse.

    Les positions restent alignées sur les bougies OHLCV d'origine.
    """
    if data is None or close is None:
        return []

    required = {
        "upper_channel",
        "lower_channel",
        "atr",
    }
    if not required <= set(data):
        return []

    frame_columns = [
        close.astype(float).rename("close"),
        data["upper_channel"].astype(float).rename("upper_channel"),
        data["lower_channel"].astype(float).rename("lower_channel"),
        data["atr"].astype(float).rename("atr"),
    ]

    invalid_ohlc = data.get("_invalid_ohlc")
    if invalid_ohlc is not None:
        frame_columns.append(invalid_ohlc.astype(float).rename("_invalid_ohlc"))

    frame = pd.concat(
        frame_columns,
        axis=1,
    ).reset_index(drop=True)

    if len(frame) < 2:
        return []

    start_position = len(frame) - 1 if only_last else 1
    events: list[IndicatorEvent] = []

    for position in range(start_position, len(frame)):
        previous = frame.iloc[position - 1]
        current = frame.iloc[position]

        raw_values = (
            previous["close"],
            previous["upper_channel"],
            previous["lower_channel"],
            current["close"],
            current["atr"],
        )

        if any(pd.isna(value) for value in raw_values):
            continue

        previous_close = float(previous["close"])
        previous_upper = float(previous["upper_channel"])
        previous_lower = float(previous["lower_channel"])
        current_close = float(current["close"])
        current_atr = float(current["atr"])

        numeric_values = (
            previous_close,
            previous_upper,
            previous_lower,
            current_close,
            current_atr,
        )

        if not all(math.isfinite(value) for value in numeric_values):
            continue

        if (
            previous_close <= 0
            or current_close <= 0
            or previous_upper <= 0
            or previous_lower < 0
            or previous_upper < previous_lower
            or current_atr < 0
        ):
            continue

        if "_invalid_ohlc" in frame.columns:
            previous_invalid = bool(previous["_invalid_ohlc"])
            current_invalid = bool(current["_invalid_ohlc"])

            if previous_invalid or current_invalid:
                continue

        breakout_up = current_close > previous_upper and previous_close <= previous_upper
        breakout_down = current_close < previous_lower and previous_close >= previous_lower

        if breakout_up:
            distance_atr = (current_close - previous_upper) / max(current_atr, 1e-12)

            events.append(
                IndicatorEvent(
                    indicator="keltner",
                    position=position,
                    direction="bullish",
                    event="breakout_up",
                    kind="breakout",
                    strength=_clamp_strength(distance_atr),
                    metadata={
                        "previous_close": previous_close,
                        "previous_reference": previous_upper,
                        "current_close": current_close,
                        "current_atr": current_atr,
                        "distance_atr": distance_atr,
                    },
                )
            )

        elif breakout_down:
            distance_atr = (previous_lower - current_close) / max(current_atr, 1e-12)

            events.append(
                IndicatorEvent(
                    indicator="keltner",
                    position=position,
                    direction="bearish",
                    event="breakout_down",
                    kind="breakout",
                    strength=_clamp_strength(distance_atr),
                    metadata={
                        "previous_close": previous_close,
                        "previous_reference": previous_lower,
                        "current_close": current_close,
                        "current_atr": current_atr,
                        "distance_atr": distance_atr,
                    },
                )
            )

    return events
