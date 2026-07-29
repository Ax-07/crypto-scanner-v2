"""Calcul du MACD, classification historique et signal structuré."""

from __future__ import annotations

import math

import pandas as pd

from app.domain.indicators.moving_averages import calculate_ema
from app.domain.indicators.types import (
    IndicatorSignal,
    MacdSignal,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = ["calculate_macd", "detect_macd_signal", "build_macd_signal"]


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

    Un croisement sur les deux derniers points est prioritaire; sinon la
    position relative courante des lignes détermine le signal.
    """
    frame = pd.concat([data["macd"], data["signal"]], axis=1).dropna()
    if len(frame) < 2:
        return "neutral"
    previous_macd, previous_signal = frame.iloc[-2]
    current_macd, current_signal = frame.iloc[-1]
    if previous_macd <= previous_signal and current_macd > current_signal:
        return "bullish"
    if previous_macd >= previous_signal and current_macd < current_signal:
        return "bearish"
    if current_macd > current_signal:
        return "bullish"
    if current_macd < current_signal:
        return "bearish"
    return "neutral"


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
