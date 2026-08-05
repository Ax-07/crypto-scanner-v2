"""Oscillateur stochastique, classification historique et signal structuré."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorEvent,
    IndicatorSignal,
    StochasticSignal,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "calculate_stochastic",
    "detect_stochastic_events",
    "detect_stochastic_signal",
    "build_stochastic_signal",
]


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


def _stochastic_components(
    *,
    current_k: float,
    current_d: float,
    previous_k: float | None,
    previous_d: float | None,
) -> dict[str, IndicatorComponent]:
    """Construit les composantes continues et causales du stochastique."""
    finite_previous_k = previous_k if previous_k is not None and math.isfinite(previous_k) else None
    finite_previous_d = previous_d if previous_d is not None and math.isfinite(previous_d) else None

    current_spread = current_k - current_d
    previous_spread = (
        finite_previous_k - finite_previous_d
        if finite_previous_k is not None and finite_previous_d is not None
        else None
    )

    k_change = current_k - finite_previous_k if finite_previous_k is not None else None
    d_change = current_d - finite_previous_d if finite_previous_d is not None else None
    spread_change = current_spread - previous_spread if previous_spread is not None else None

    return {
        "k": IndicatorComponent(
            value=current_k,
            normalized_value=current_k / 100.0,
            unit="index",
        ),
        "d": IndicatorComponent(
            value=current_d,
            normalized_value=current_d / 100.0,
            unit="index",
        ),
        "spread": IndicatorComponent(
            value=current_spread,
            normalized_value=current_spread / 100.0,
            unit="index",
        ),
        "previous_k": IndicatorComponent(
            value=finite_previous_k,
            normalized_value=(finite_previous_k / 100.0 if finite_previous_k is not None else None),
            unit="index",
        ),
        "previous_d": IndicatorComponent(
            value=finite_previous_d,
            normalized_value=(finite_previous_d / 100.0 if finite_previous_d is not None else None),
            unit="index",
        ),
        "previous_spread": IndicatorComponent(
            value=previous_spread,
            normalized_value=(previous_spread / 100.0 if previous_spread is not None else None),
            unit="index",
        ),
        "k_change": IndicatorComponent(
            value=k_change,
            normalized_value=k_change / 100.0 if k_change is not None else None,
            unit="index",
        ),
        "d_change": IndicatorComponent(
            value=d_change,
            normalized_value=d_change / 100.0 if d_change is not None else None,
            unit="index",
        ),
        "spread_change": IndicatorComponent(
            value=spread_change,
            normalized_value=(spread_change / 100.0 if spread_change is not None else None),
            unit="index",
        ),
    }


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

    previous_k: float | None = None
    previous_d: float | None = None
    event: str | None = None

    if len(frame) >= 2:
        previous_k = float(frame["k"].iloc[-2])
        previous_d = float(frame["d"].iloc[-2])

        if previous_k <= previous_d and current_k > current_d:
            event = "bullish_cross"
        elif previous_k >= previous_d and current_k < current_d:
            event = "bearish_cross"

    components = _stochastic_components(
        current_k=current_k,
        current_d=current_d,
        previous_k=previous_k,
        previous_d=previous_d,
    )

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
            components=components,
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
            components=components,
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
            components=components,
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
            components=components,
        )
    return IndicatorSignal(
        status="available",
        direction="neutral",
        signal=state,
        state=state,
        strength=0.0,
        reason="Stochastique en zone neutre",
        raw_value=current_k,
        components=components,
    )


def detect_stochastic_events(
    data: dict[str, pd.Series] | None,
    oversold_level: float = 20,
    overbought_level: float = 80,
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les croisements du stochastique dans les zones extrêmes.

    Un événement haussier est produit lorsque %K croise au-dessus de %D
    alors que le croisement se déroule dans ou à proximité immédiate de la
    zone de survente.

    Un événement baissier est produit lorsque %K croise sous %D dans ou à
    proximité immédiate de la zone de surachat.

    Les positions restent alignées sur les bougies OHLCV d'origine.
    """
    if data is None:
        return []

    k_series = data.get("k")
    d_series = data.get("d")

    if k_series is None or d_series is None:
        return []

    k_values = pd.to_numeric(
        k_series.reset_index(drop=True),
        errors="coerce",
    )
    d_values = pd.to_numeric(
        d_series.reset_index(drop=True),
        errors="coerce",
    )

    length = min(len(k_values), len(d_values))
    if length < 2:
        return []

    start_position = length - 1 if only_last else 1
    events: list[IndicatorEvent] = []

    for position in range(start_position, length):
        previous_k_raw = k_values.iloc[position - 1]
        previous_d_raw = d_values.iloc[position - 1]
        current_k_raw = k_values.iloc[position]
        current_d_raw = d_values.iloc[position]

        values = (
            previous_k_raw,
            previous_d_raw,
            current_k_raw,
            current_d_raw,
        )

        if any(pd.isna(value) for value in values):
            continue

        previous_k = float(previous_k_raw)
        previous_d = float(previous_d_raw)
        current_k = float(current_k_raw)
        current_d = float(current_d_raw)

        if not all(
            math.isfinite(value)
            for value in (
                previous_k,
                previous_d,
                current_k,
                current_d,
            )
        ):
            continue

        bullish_cross = previous_k <= previous_d and current_k > current_d
        bearish_cross = previous_k >= previous_d and current_k < current_d

        # Le croisement peut faire sortir %K de la zone extrême sur la
        # bougie courante. On accepte donc la zone précédente ou actuelle.
        bullish_extreme_zone = (previous_k <= oversold_level and previous_d <= oversold_level) or (
            current_k <= oversold_level and current_d <= oversold_level
        )

        bearish_extreme_zone = (
            previous_k >= overbought_level and previous_d >= overbought_level
        ) or (current_k >= overbought_level and current_d >= overbought_level)

        if bullish_cross and bullish_extreme_zone:
            events.append(
                IndicatorEvent(
                    indicator="stochastic",
                    position=position,
                    direction="bullish",
                    event="bullish_cross",
                    kind="cross",
                    strength=1.0,
                    metadata={
                        "previous_k": previous_k,
                        "previous_d": previous_d,
                        "current_k": current_k,
                        "current_d": current_d,
                        "oversold_level": oversold_level,
                    },
                )
            )

        elif bearish_cross and bearish_extreme_zone:
            events.append(
                IndicatorEvent(
                    indicator="stochastic",
                    position=position,
                    direction="bearish",
                    event="bearish_cross",
                    kind="cross",
                    strength=1.0,
                    metadata={
                        "previous_k": previous_k,
                        "previous_d": previous_d,
                        "current_k": current_k,
                        "current_d": current_d,
                        "overbought_level": overbought_level,
                    },
                )
            )

    return events
