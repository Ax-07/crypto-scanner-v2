"""Calcul du MACD, classification historique et signal structuré."""

from __future__ import annotations

import math

import pandas as pd

from app.domain.indicators.moving_averages import calculate_ema
from app.domain.indicators.types import (
    IndicatorEvent,
    IndicatorSignal,
    MacdSignal,
    SignalDirection,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "calculate_macd",
    "detect_macd_signal",
    "build_macd_signal",
    "detect_macd_events",
]


def calculate_macd(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, pd.Series]:
    """Calcule les lignes MACD, signal et histogramme à partir des clôtures."""
    fast = calculate_ema(close, fast_period)
    slow = calculate_ema(close, slow_period)
    macd = fast - slow
    signal = macd.ewm(span=signal_period, adjust=False, min_periods=signal_period).mean()
    histogram = macd - signal
    return {"macd": macd, "signal": signal, "histogram": histogram}


def detect_macd_signal(data: dict[str, pd.Series]) -> MacdSignal:
    """Classe le MACD en ``bullish``, ``bearish`` ou ``neutral``.

    Un croisement entre la ligne MACD et sa ligne de signal sur les deux
    derniers points valides est prioritaire. En l'absence de croisement,
    leur position relative actuelle détermine le signal.
    """
    macd_series = data.get("macd")
    signal_series = data.get("signal")

    if macd_series is None or signal_series is None:
        return "neutral"

    frame = pd.concat(
        [
            macd_series.rename("macd"),
            signal_series.rename("signal"),
        ],
        axis=1,
    ).dropna()

    if len(frame) < 2:
        return "neutral"

    previous_macd = float(frame["macd"].iloc[-2])
    previous_signal = float(frame["signal"].iloc[-2])
    current_macd = float(frame["macd"].iloc[-1])
    current_signal = float(frame["signal"].iloc[-1])

    if not all(
        math.isfinite(value)
        for value in (
            previous_macd,
            previous_signal,
            current_macd,
            current_signal,
        )
    ):
        return "neutral"

    if previous_macd <= previous_signal and current_macd > current_signal:
        return "bullish"

    if previous_macd >= previous_signal and current_macd < current_signal:
        return "bearish"

    if current_macd > current_signal:
        return "bullish"

    if current_macd < current_signal:
        return "bearish"

    return "neutral"


def detect_macd_events(
    data: dict[str, pd.Series] | None,
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les croisements ponctuels MACD/ligne de signal.

    Le passage de l'histogramme par zéro est équivalent au croisement entre
    la ligne MACD et sa ligne de signal. La position reste celle des séries
    originales afin de pouvoir lui associer le timestamp OHLCV correspondant.
    """
    if data is None:
        return []

    macd = data.get("macd")
    signal = data.get("signal")

    if macd is None or signal is None:
        return []

    macd_values = pd.to_numeric(
        macd.reset_index(drop=True),
        errors="coerce",
    )
    signal_values = pd.to_numeric(
        signal.reset_index(drop=True),
        errors="coerce",
    )

    if len(macd_values) != len(signal_values) or len(macd_values) < 2:
        return []

    histogram = data.get("histogram")
    histogram_values = (
        pd.to_numeric(
            histogram.reset_index(drop=True),
            errors="coerce",
        )
        if histogram is not None
        else None
    )

    start_position = len(macd_values) - 1 if only_last else 1
    events: list[IndicatorEvent] = []

    for position in range(start_position, len(macd_values)):
        previous_macd_raw = macd_values.iloc[position - 1]
        previous_signal_raw = signal_values.iloc[position - 1]
        current_macd_raw = macd_values.iloc[position]
        current_signal_raw = signal_values.iloc[position]

        if any(
            pd.isna(value)
            for value in (
                previous_macd_raw,
                previous_signal_raw,
                current_macd_raw,
                current_signal_raw,
            )
        ):
            continue

        previous_macd = float(previous_macd_raw)
        previous_signal = float(previous_signal_raw)
        current_macd = float(current_macd_raw)
        current_signal = float(current_signal_raw)

        if not all(
            math.isfinite(value)
            for value in (
                previous_macd,
                previous_signal,
                current_macd,
                current_signal,
            )
        ):
            continue

        direction: SignalDirection
        event_name: str

        if previous_macd <= previous_signal and current_macd > current_signal:
            direction = "bullish"
            event_name = "bullish_cross"

        elif previous_macd >= previous_signal and current_macd < current_signal:
            direction = "bearish"
            event_name = "bearish_cross"

        else:
            continue

        denominator = abs(current_macd) + abs(current_signal)
        relative_distance = (
            abs(current_macd - current_signal) / denominator
            if denominator > 1e-12
            else 0.0
        )

        zero_confirmation = (
            direction == "bullish" and current_macd > 0
        ) or (
            direction == "bearish" and current_macd < 0
        )

        strength = _clamp_strength(
            0.75
            + (0.15 if zero_confirmation else 0.0)
            + min(relative_distance, 0.1)
        )

        metadata: dict[str, object] = {
            "previous_macd": previous_macd,
            "previous_signal": previous_signal,
            "current_macd": current_macd,
            "current_signal": current_signal,
            "relative_distance": relative_distance,
            "zero_confirmation": zero_confirmation,
        }

        if (
            histogram_values is not None
            and position < len(histogram_values)
            and not pd.isna(histogram_values.iloc[position])
        ):
            current_histogram = float(histogram_values.iloc[position])

            if math.isfinite(current_histogram):
                metadata["current_histogram"] = current_histogram

        events.append(
            IndicatorEvent(
                indicator="macd",
                position=position,
                direction=direction,
                event=event_name,
                kind="cross",
                strength=strength,
                metadata=metadata,
            )
        )

    return events


def build_macd_signal(data: dict[str, pd.Series]) -> IndicatorSignal:
    """Construit le signal structuré du MACD.

    Un croisement récent (deux derniers points) est prioritaire sur l'état
    persistant par rapport à la ligne de signal. Le champ ``state`` combine
    cet état persistant (``above_signal``/``below_signal``/``neutral``) et la
    position par rapport à zéro (``above_zero``/``below_zero``/``at_zero``),
    sous la forme ``"<etat_ligne>/<position_zero>"``.

    La force part de ``0.75`` pour un croisement (``0.5`` pour un état
    persistant), puis reçoit un bonus borné tenant compte de la cohérence
    avec la position par rapport à zéro et de la distance relative entre le
    MACD et sa ligne de signal (normalisée par leur amplitude, donc
    indépendante de l'échelle absolue du prix).
    """
    frame = pd.concat(
        [data["macd"].rename("macd"), data["signal"].rename("signal")], axis=1
    ).dropna()
    if frame.empty:
        return _unavailable_signal("insufficient_data", "Historique de MACD insuffisant")

    current_macd, current_signal = float(frame["macd"].iloc[-1]), float(frame["signal"].iloc[-1])
    if not (math.isfinite(current_macd) and math.isfinite(current_signal)):
        return _unavailable_signal("invalid_data", "Valeurs de MACD non finies")

    zero_state = (
        "above_zero" if current_macd > 0 else "below_zero" if current_macd < 0 else "at_zero"
    )
    if current_macd > current_signal:
        line_state = "above_signal"
    elif current_macd < current_signal:
        line_state = "below_signal"
    else:
        line_state = "neutral"
    state = f"{line_state}/{zero_state}"

    denominator = abs(current_macd) + abs(current_signal)
    relative_distance = (
        abs(current_macd - current_signal) / denominator if denominator > 1e-12 else 0.0
    )

    event: str | None = None
    if len(frame) >= 2:
        previous_macd = float(frame["macd"].iloc[-2])
        previous_signal = float(frame["signal"].iloc[-2])
        if previous_macd <= previous_signal and current_macd > current_signal:
            event = "bullish_cross"
        elif previous_macd >= previous_signal and current_macd < current_signal:
            event = "bearish_cross"

    if event == "bullish_cross":
        strength = _clamp_strength(
            0.75 + (0.15 if zero_state == "above_zero" else 0.0) + min(relative_distance, 0.1)
        )
        return IndicatorSignal(
            status="available",
            direction="bullish",
            signal=event,
            state=state,
            strength=strength,
            reason="Croisement haussier du MACD au-dessus de sa ligne de signal",
            raw_value=current_macd,
        )
    if event == "bearish_cross":
        strength = _clamp_strength(
            0.75 + (0.15 if zero_state == "below_zero" else 0.0) + min(relative_distance, 0.1)
        )
        return IndicatorSignal(
            status="available",
            direction="bearish",
            signal=event,
            state=state,
            strength=strength,
            reason="Croisement baissier du MACD sous sa ligne de signal",
            raw_value=current_macd,
        )
    if line_state == "above_signal":
        strength = _clamp_strength(0.5 + min(relative_distance, 0.25))
        return IndicatorSignal(
            status="available",
            direction="bullish",
            signal=line_state,
            state=state,
            strength=strength,
            reason="MACD maintenu au-dessus de sa ligne de signal",
            raw_value=current_macd,
        )
    if line_state == "below_signal":
        strength = _clamp_strength(0.5 + min(relative_distance, 0.25))
        return IndicatorSignal(
            status="available",
            direction="bearish",
            signal=line_state,
            state=state,
            strength=strength,
            reason="MACD maintenu sous sa ligne de signal",
            raw_value=current_macd,
        )
    return IndicatorSignal(
        status="available",
        direction="neutral",
        signal=line_state,
        state=state,
        strength=0.0,
        reason="MACD proche de sa ligne de signal, position neutre",
        raw_value=current_macd,
    )
