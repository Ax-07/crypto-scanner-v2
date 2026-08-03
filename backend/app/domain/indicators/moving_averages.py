"""Moyennes mobiles (SMA/EMA), classification de tendance et signal structuré."""

from __future__ import annotations

import math
from typing import Literal

import pandas as pd

from app.domain.indicators.types import (
    IndicatorEvent,
    IndicatorSignal,
    SignalDirection,
    TrendState,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "calculate_sma",
    "calculate_ema",
    "detect_trend",
    "detect_moving_average_signal",
    "detect_moving_average_events",
]

MovingAverageFamily = Literal["sma", "ema"]


def calculate_sma(close: pd.Series, period: int) -> pd.Series:
    """Calcule une moyenne mobile arithmétique sur ``period`` clôtures."""
    return close.astype(float).rolling(period, min_periods=period).mean()


def calculate_ema(close: pd.Series, period: int) -> pd.Series:
    """Calcule une moyenne mobile exponentielle sans valeur avant l'amorçage."""
    return close.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def detect_trend(
    close: pd.Series,
    sma_fast: float | None,
    sma_slow: float | None,
    ema_fast: float | None,
    ema_slow: float | None,
) -> TrendState:
    """Classe la tendance sans transformer un désaccord SMA/EMA en hausse."""
    price = float(close.iloc[-1])

    def family(fast: float | None, slow: float | None) -> TrendState:
        if fast is None:
            return "unavailable"
        if slow is None:
            return "bullish" if price > fast else "bearish" if price < fast else "neutral"
        if fast > slow and price > fast:
            return "bullish"
        if fast < slow and price < fast:
            return "bearish"
        return "neutral"

    states: list[TrendState] = []
    if sma_fast is not None:
        states.append(family(sma_fast, sma_slow))
    if ema_fast is not None:
        states.append(family(ema_fast, ema_slow))
    if not states:
        return "unavailable"
    if len(states) == 1:
        return states[0]
    return states[0] if states[0] == states[1] else "neutral"


_MOVING_AVERAGE_SIGNAL_STRENGTH: dict[str, float] = {
    "bullish_cross": 0.75,
    "bearish_cross": 0.75,
    "bullish_alignment": 0.5,
    "bearish_alignment": 0.5,
    "price_above": 0.25,
    "price_below": 0.25,
    "neutral": 0.0,
}

_MOVING_AVERAGE_SIGNAL_DIRECTION: dict[str, SignalDirection] = {
    "bullish_cross": "bullish",
    "bearish_cross": "bearish",
    "bullish_alignment": "bullish",
    "bearish_alignment": "bearish",
    "price_above": "bullish",
    "price_below": "bearish",
    "neutral": "neutral",
}


def _moving_average_signal(
    family_label: str, signal: str, reason: str, *, raw_value: float | None = None
) -> IndicatorSignal:
    return IndicatorSignal(
        status="available",
        direction=_MOVING_AVERAGE_SIGNAL_DIRECTION[signal],
        signal=signal,
        state=None,
        strength=_clamp_strength(_MOVING_AVERAGE_SIGNAL_STRENGTH[signal]),
        reason=f"{family_label.upper()}: {reason}",
        raw_value=raw_value,
    )


def detect_moving_average_events(
    fast: pd.Series | None,
    slow: pd.Series | None,
    *,
    family: MovingAverageFamily,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les croisements ponctuels entre moyennes rapide et lente.

    La position retournée correspond à l'index dans les séries originales.
    Une simple configuration haussière ou baissière persistante ne produit
    aucun événement : seuls les changements de côté sont conservés.
    """
    if fast is None or slow is None:
        return []

    fast_values = pd.to_numeric(
        fast.reset_index(drop=True),
        errors="coerce",
    )
    slow_values = pd.to_numeric(
        slow.reset_index(drop=True),
        errors="coerce",
    )

    if len(fast_values) != len(slow_values) or len(fast_values) < 2:
        return []

    start_position = len(fast_values) - 1 if only_last else 1
    events: list[IndicatorEvent] = []

    for position in range(start_position, len(fast_values)):
        previous_fast_raw = fast_values.iloc[position - 1]
        previous_slow_raw = slow_values.iloc[position - 1]
        current_fast_raw = fast_values.iloc[position]
        current_slow_raw = slow_values.iloc[position]

        if any(
            pd.isna(value)
            for value in (
                previous_fast_raw,
                previous_slow_raw,
                current_fast_raw,
                current_slow_raw,
            )
        ):
            continue

        previous_fast = float(previous_fast_raw)
        previous_slow = float(previous_slow_raw)
        current_fast = float(current_fast_raw)
        current_slow = float(current_slow_raw)

        if not all(
            math.isfinite(value)
            for value in (
                previous_fast,
                previous_slow,
                current_fast,
                current_slow,
            )
        ):
            continue

        if previous_fast <= previous_slow and current_fast > current_slow:
            events.append(
                IndicatorEvent(
                    indicator=family,
                    position=position,
                    direction="bullish",
                    event="bullish_cross",
                    kind="cross",
                    strength=_MOVING_AVERAGE_SIGNAL_STRENGTH[
                        "bullish_cross"
                    ],
                    metadata={
                        "previous_fast": previous_fast,
                        "previous_slow": previous_slow,
                        "current_fast": current_fast,
                        "current_slow": current_slow,
                    },
                )
            )

        elif previous_fast >= previous_slow and current_fast < current_slow:
            events.append(
                IndicatorEvent(
                    indicator=family,
                    position=position,
                    direction="bearish",
                    event="bearish_cross",
                    kind="cross",
                    strength=_MOVING_AVERAGE_SIGNAL_STRENGTH[
                        "bearish_cross"
                    ],
                    metadata={
                        "previous_fast": previous_fast,
                        "previous_slow": previous_slow,
                        "current_fast": current_fast,
                        "current_slow": current_slow,
                    },
                )
            )

    return events


def detect_moving_average_signal(
    close: pd.Series,
    fast: pd.Series,
    slow: pd.Series | None,
    *,
    family: MovingAverageFamily,
) -> IndicatorSignal:
    """Construit le signal structuré d'une famille de moyennes mobiles (SMA ou EMA).

    Le croisement entre moyenne rapide et lente est prioritaire. Sans moyenne
    lente, le prix est comparé à la seule moyenne disponible. Un alignement
    haussier exige au minimum ``prix > rapide > lente``, un alignement
    baissier ``prix < rapide < lente``; toute autre configuration avec une
    moyenne lente est neutre. Chaque famille (SMA, EMA) doit être appelée
    séparément: cette fonction ne mélange jamais les deux séries.

    La force suit la convention du package: ``0.75`` pour un croisement,
    ``0.5`` pour un alignement, ``0.25`` pour une simple comparaison
    prix/moyenne, ``0.0`` en configuration neutre ou contradictoire.
    """
    series = {"price": close, "fast": fast}
    if slow is not None:
        series["slow"] = slow
    frame = pd.concat(
        [item.rename(name) for name, item in series.items()],
        axis=1,
    ).dropna()
    if frame.empty:
        return _unavailable_signal("insufficient_data", "Historique de moyenne mobile insuffisant")

    price = float(frame["price"].iloc[-1])
    fast_value = float(frame["fast"].iloc[-1])
    if not (math.isfinite(price) and math.isfinite(fast_value)):
        return _unavailable_signal("invalid_data", "Valeur de moyenne mobile non finie")

    if slow is not None:
        slow_value = float(frame["slow"].iloc[-1])
        if not math.isfinite(slow_value):
            return _unavailable_signal("invalid_data", "Valeur de moyenne mobile non finie")
        if len(frame) >= 2:
            previous_fast = float(frame["fast"].iloc[-2])
            previous_slow = float(frame["slow"].iloc[-2])
            if not (math.isfinite(previous_fast) and math.isfinite(previous_slow)):
                return _unavailable_signal("invalid_data", "Valeur de moyenne mobile non finie")
            if previous_fast <= previous_slow and fast_value > slow_value:
                return _moving_average_signal(
                    family,
                    "bullish_cross",
                    "croisement haussier rapide/lente",
                    raw_value=fast_value,
                )
            if previous_fast >= previous_slow and fast_value < slow_value:
                return _moving_average_signal(
                    family,
                    "bearish_cross",
                    "croisement baissier rapide/lente",
                    raw_value=fast_value,
                )
        if price > fast_value > slow_value:
            return _moving_average_signal(
                family,
                "bullish_alignment",
                "alignement haussier prix > rapide > lente",
                raw_value=fast_value,
            )
        if price < fast_value < slow_value:
            return _moving_average_signal(
                family,
                "bearish_alignment",
                "alignement baissier prix < rapide < lente",
                raw_value=fast_value,
            )
        return _moving_average_signal(
            family, "neutral", "configuration contradictoire", raw_value=fast_value
        )

    if price > fast_value:
        return _moving_average_signal(
            family, "price_above", "prix au-dessus de la moyenne", raw_value=fast_value
        )
    if price < fast_value:
        return _moving_average_signal(
            family, "price_below", "prix en dessous de la moyenne", raw_value=fast_value
        )
    return _moving_average_signal(
        family, "neutral", "prix aligné sur la moyenne", raw_value=fast_value
    )
