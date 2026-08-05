"""Calcul du RSI de Wilder et signal structuré associé."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorEvent,
    IndicatorSignal,
    SignalDirection,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "calculate_rsi",
    "get_latest_rsi",
    "detect_rsi_events",
    "detect_rsi_signal",
]


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calcule le RSI de Wilder par moyennes exponentielles des gains et pertes.

    Les valeurs restent absentes durant la période d'amorçage. Une perte moyenne
    nulle après amorçage donne un RSI de 100.
    """
    delta = close.astype(float).diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100).where(avg_gain.notna())


def get_latest_rsi(close: pd.Series, period: int = 14) -> float | None:
    """Retourne le dernier RSI calculable, ou ``None`` si l'historique est insuffisant."""
    values = calculate_rsi(close, period).dropna()
    return float(values.iloc[-1]) if not values.empty else None


def _extract_last_two(rsi: pd.Series | float | None) -> tuple[float | None, float | None]:
    """Retourne ``(valeur précédente, valeur courante)`` du RSI fourni.

    Une série est d'abord purgée de ses ``NaN`` pour ne considérer que les
    valeurs réellement calculables. Une valeur scalaire n'a pas de précédent
    connu. ``None`` est retourné pour la valeur courante en l'absence de
    donnée exploitable.
    """
    if rsi is None:
        return None, None
    if isinstance(rsi, (int, float)):
        return None, float(rsi)
    valid = rsi.dropna()
    if valid.empty:
        return None, None
    if len(valid) == 1:
        return None, float(valid.iloc[-1])
    return float(valid.iloc[-2]), float(valid.iloc[-1])


def _rsi_state(value: float, oversold_level: float, overbought_level: float) -> str:
    """Classe une valeur de RSI en 5 zones déterministes.

    Les zones ``near_oversold``/``near_overbought`` occupent chacune 25 % de
    l'écart entre les niveaux de survente et de surachat, adjacentes aux
    zones extrêmes; le reste de la plage est ``neutral``.
    """
    if value <= oversold_level:
        return "oversold"
    if value >= overbought_level:
        return "overbought"
    near_band = (overbought_level - oversold_level) * 0.25
    if value < oversold_level + near_band:
        return "near_oversold"
    if value > overbought_level - near_band:
        return "near_overbought"
    return "neutral"


def _rsi_components(
    *,
    previous_value: float | None,
    current_value: float,
    oversold_level: float,
    overbought_level: float,
) -> dict[str, IndicatorComponent]:
    """Construit les composantes continues et normalisées du RSI.

    Toutes les valeurs sont causales : elles utilisent uniquement la valeur
    courante et, lorsqu'elle existe, la valeur immédiatement précédente.
    """
    finite_previous = (
        previous_value if previous_value is not None and math.isfinite(previous_value) else None
    )
    change = current_value - finite_previous if finite_previous is not None else None

    return {
        "rsi": IndicatorComponent(
            value=current_value,
            normalized_value=current_value / 100.0,
            unit="index",
        ),
        "previous_value": IndicatorComponent(
            value=finite_previous,
            normalized_value=(finite_previous / 100.0 if finite_previous is not None else None),
            unit="index",
        ),
        "change": IndicatorComponent(
            value=change,
            normalized_value=change / 100.0 if change is not None else None,
            unit="index",
        ),
        "distance_from_midpoint": IndicatorComponent(
            value=current_value - 50.0,
            normalized_value=(current_value - 50.0) / 100.0,
            unit="index",
        ),
        "distance_from_oversold": IndicatorComponent(
            value=current_value - oversold_level,
            normalized_value=(current_value - oversold_level) / 100.0,
            unit="index",
        ),
        "distance_from_overbought": IndicatorComponent(
            value=current_value - overbought_level,
            normalized_value=(current_value - overbought_level) / 100.0,
            unit="index",
        ),
    }


_RSI_STATE_DIRECTION: dict[str, SignalDirection] = {
    "oversold": "bullish",
    "near_oversold": "bullish",
    "neutral": "neutral",
    "near_overbought": "bearish",
    "overbought": "bearish",
}

#: Force associée à chaque état RSI selon la convention du package
#: (0.0 = aucune information, 1.0 = signal maximal).
_RSI_STATE_STRENGTH: dict[str, float] = {
    "oversold": 1.0,
    "near_oversold": 0.5,
    "neutral": 0.0,
    "near_overbought": 0.5,
    "overbought": 1.0,
}


def detect_rsi_signal(
    rsi: pd.Series | float | None,
    oversold_level: float = 30,
    overbought_level: float = 70,
) -> IndicatorSignal:
    """Construit le signal structuré du RSI.

    Une sortie de zone extrême (``exit_oversold``/``exit_overbought``) entre
    les deux dernières valeurs de la série est prioritaire sur le simple état
    courant. Sans historique (valeur scalaire ou série d'une seule valeur
    valide), seul l'état courant est déterminé.

    La force suit la convention du package: ``1.0`` en zone extrême,
    ``0.75`` pour une sortie de zone (événement significatif), ``0.5`` dans
    les zones intermédiaires et ``0.0`` en zone neutre ou donnée absente.
    """
    previous_value, current_value = _extract_last_two(rsi)
    if current_value is None:
        return _unavailable_signal("insufficient_data", "Historique de RSI insuffisant")
    if not math.isfinite(current_value):
        return _unavailable_signal("invalid_data", "Valeur de RSI non finie")

    components = _rsi_components(
        previous_value=previous_value,
        current_value=current_value,
        oversold_level=oversold_level,
        overbought_level=overbought_level,
    )

    if previous_value is not None and math.isfinite(previous_value):
        if previous_value <= oversold_level and current_value > oversold_level:
            return IndicatorSignal(
                status="available",
                direction="bullish",
                signal="exit_oversold",
                state=_rsi_state(current_value, oversold_level, overbought_level),
                strength=_clamp_strength(0.75),
                reason=f"RSI sort de la zone de survente ({current_value:.2f})",
                raw_value=current_value,
                components=components,
            )
        if previous_value >= overbought_level and current_value < overbought_level:
            return IndicatorSignal(
                status="available",
                direction="bearish",
                signal="exit_overbought",
                state=_rsi_state(current_value, oversold_level, overbought_level),
                strength=_clamp_strength(0.75),
                reason=f"RSI sort de la zone de surachat ({current_value:.2f})",
                raw_value=current_value,
                components=components,
            )

    state = _rsi_state(current_value, oversold_level, overbought_level)
    return IndicatorSignal(
        status="available",
        direction=_RSI_STATE_DIRECTION[state],
        signal=state,
        state=state,
        strength=_clamp_strength(_RSI_STATE_STRENGTH[state]),
        reason=f"RSI en zone {state} ({current_value:.2f})",
        raw_value=current_value,
        components=components,
    )


def detect_rsi_events(
    rsi: pd.Series | None,
    oversold_level: float = 30,
    overbought_level: float = 70,
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les sorties ponctuelles des zones extrêmes du RSI.

    Une sortie de survente est haussière lorsque le RSI passe d'une valeur
    inférieure ou égale au seuil de survente à une valeur supérieure.

    Une sortie de surachat est baissière lorsque le RSI passe d'une valeur
    supérieure ou égale au seuil de surachat à une valeur inférieure.

    Args:
        rsi: Série RSI alignée sur les bougies OHLCV.
        oversold_level: Seuil de survente.
        overbought_level: Seuil de surachat.
        only_last: Lorsque vrai, évalue uniquement la dernière position.

    Returns:
        Les événements RSI détectés avec leur position dans la série.
    """
    if rsi is None:
        return []

    values = pd.to_numeric(
        rsi.reset_index(drop=True),
        errors="coerce",
    )

    if len(values) < 2:
        return []

    start_position = len(values) - 1 if only_last else 1
    events: list[IndicatorEvent] = []

    for position in range(start_position, len(values)):
        previous_raw = values.iloc[position - 1]
        current_raw = values.iloc[position]

        if pd.isna(previous_raw) or pd.isna(current_raw):
            continue

        previous_value = float(previous_raw)
        current_value = float(current_raw)

        if not math.isfinite(previous_value) or not math.isfinite(current_value):
            continue

        if previous_value <= oversold_level < current_value:
            events.append(
                IndicatorEvent(
                    indicator="rsi",
                    position=position,
                    direction="bullish",
                    event="exit_oversold",
                    kind="threshold_exit",
                    strength=0.75,
                    metadata={
                        "previous_value": previous_value,
                        "current_value": current_value,
                        "threshold": oversold_level,
                    },
                )
            )

        elif previous_value >= overbought_level > current_value:
            events.append(
                IndicatorEvent(
                    indicator="rsi",
                    position=position,
                    direction="bearish",
                    event="exit_overbought",
                    kind="threshold_exit",
                    strength=0.75,
                    metadata={
                        "previous_value": previous_value,
                        "current_value": current_value,
                        "threshold": overbought_level,
                    },
                )
            )

    return events
