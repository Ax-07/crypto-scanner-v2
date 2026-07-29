"""Oscillateur stochastique, classification historique et signal structuré."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.types import (
    IndicatorSignal,
    StochasticSignal,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = ["calculate_stochastic", "detect_stochastic_signal", "build_stochastic_signal"]


def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> dict[str, pd.Series]:
    """Calcule l'oscillateur stochastique ``%K`` et sa moyenne ``%D``."""
    lowest = low.astype(float).rolling(k_period, min_periods=k_period).min()
    highest = high.astype(float).rolling(k_period, min_periods=k_period).max()
    denominator = (highest - lowest).replace(0, np.nan)
    k = ((close.astype(float) - lowest) / denominator) * 100
    d = k.rolling(d_period, min_periods=d_period).mean()
    return {"k": k, "d": d}


def detect_stochastic_signal(
    data: dict[str, pd.Series],
    oversold_level: float = 20,
    overbought_level: float = 80,
) -> StochasticSignal:
    """Détecte d'abord un croisement, puis une zone extrême du stochastique."""
    frame = pd.concat([data["k"], data["d"]], axis=1).dropna()
    if len(frame) < 2:
        return "neutral"
    previous_k, previous_d = frame.iloc[-2]
    current_k, current_d = frame.iloc[-1]
    if previous_k <= previous_d and current_k > current_d:
        return "bullish_cross"
    if previous_k >= previous_d and current_k < current_d:
        return "bearish_cross"
    if current_k <= oversold_level and current_d <= oversold_level:
        return "oversold"
    if current_k >= overbought_level and current_d >= overbought_level:
        return "overbought"
    return "neutral"


def build_stochastic_signal(
    data: dict[str, pd.Series],
    oversold_level: float = 20,
    overbought_level: float = 80,
) -> IndicatorSignal:
    """Construit le signal structuré de l'oscillateur stochastique.

    Un croisement entre les deux derniers points est prioritaire sur la zone
    courante, elle-même conservée dans ``state`` même lorsqu'un croisement
    est détecté. Un croisement haussier en zone de survente est plus fort
    qu'un croisement haussier hors zone extrême (même principe, symétrique,
    pour un croisement baissier en zone de surachat).

    Force retenue: ``1.0`` pour un croisement dans sa zone extrême
    correspondante, ``0.6`` pour un croisement hors zone extrême, ``0.5`` pour
    un état extrême sans croisement, ``0.0`` en zone neutre.
    """
    frame = pd.concat([data["k"].rename("k"), data["d"].rename("d")], axis=1).dropna()
    if frame.empty:
        return _unavailable_signal("insufficient_data", "Historique de stochastique insuffisant")

    current_k, current_d = float(frame["k"].iloc[-1]), float(frame["d"].iloc[-1])
    if not (math.isfinite(current_k) and math.isfinite(current_d)):
        return _unavailable_signal("invalid_data", "Valeurs de stochastique non finies")

    if current_k <= oversold_level and current_d <= oversold_level:
        state = "oversold"
    elif current_k >= overbought_level and current_d >= overbought_level:
        state = "overbought"
    else:
        state = "neutral"

    event: str | None = None
    if len(frame) >= 2:
        previous_k, previous_d = float(frame["k"].iloc[-2]), float(frame["d"].iloc[-2])
        if previous_k <= previous_d and current_k > current_d:
            event = "bullish_cross"
        elif previous_k >= previous_d and current_k < current_d:
            event = "bearish_cross"

    if event == "bullish_cross":
        strength = 1.0 if state == "oversold" else 0.6
        reason = "Croisement haussier du stochastique" + (
            " en zone de survente" if state == "oversold" else ""
        )
        return IndicatorSignal(
            status="available",
            direction="bullish",
            signal=event,
            state=state,
            strength=_clamp_strength(strength),
            reason=reason,
            raw_value=current_k,
        )
    if event == "bearish_cross":
        strength = 1.0 if state == "overbought" else 0.6
        reason = "Croisement baissier du stochastique" + (
            " en zone de surachat" if state == "overbought" else ""
        )
        return IndicatorSignal(
            status="available",
            direction="bearish",
            signal=event,
            state=state,
            strength=_clamp_strength(strength),
            reason=reason,
            raw_value=current_k,
        )
    if state == "oversold":
        return IndicatorSignal(
            status="available",
            direction="bullish",
            signal=state,
            state=state,
            strength=_clamp_strength(0.5),
            reason="Stochastique en zone de survente sans croisement",
            raw_value=current_k,
        )
    if state == "overbought":
        return IndicatorSignal(
            status="available",
            direction="bearish",
            signal=state,
            state=state,
            strength=_clamp_strength(0.5),
            reason="Stochastique en zone de surachat sans croisement",
            raw_value=current_k,
        )
    return IndicatorSignal(
        status="available",
        direction="neutral",
        signal=state,
        state=state,
        strength=0.0,
        reason="Stochastique en zone neutre",
        raw_value=current_k,
    )
