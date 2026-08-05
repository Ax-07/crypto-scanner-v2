"""Directional Movement Index, DX, ADX et signal structuré."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorComponentUnit,
    IndicatorEvent,
    IndicatorSignal,
    SignalDirection,
    _clamp_strength,
    _unavailable_signal,
)
from app.domain.indicators.wilder import (
    calculate_directional_movement,
    calculate_true_range,
    wilder_smoothing,
)

__all__ = [
    "build_adx_signal",
    "calculate_adx_dmi",
    "detect_adx_events",
]


def calculate_adx_dmi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    *,
    true_range: pd.Series | None = None,
) -> dict[str, pd.Series]:
    """Calcule +DI, -DI, DX et ADX selon les amorçages de Wilder.

    +DM/-DM commencent à zéro sur la première bougie. Les premiers DMI sont
    disponibles à l'index ``period - 1`` et le premier ADX à
    ``2 * period - 2`` (27 bougies pour une période 14).
    """
    tr = true_range if true_range is not None else calculate_true_range(high, low, close)
    movement = calculate_directional_movement(high, low)
    smoothed_tr = wilder_smoothing(tr, period)
    smoothed_plus = wilder_smoothing(movement["plus_dm"], period)
    smoothed_minus = wilder_smoothing(movement["minus_dm"], period)

    plus_di = pd.Series(np.nan, index=tr.index, dtype=float, name="plus_di")
    minus_di = pd.Series(np.nan, index=tr.index, dtype=float, name="minus_di")
    ready = smoothed_tr.notna() & smoothed_plus.notna() & smoothed_minus.notna()
    positive = ready & (smoothed_tr > 0)
    zero = ready & (smoothed_tr == 0)
    plus_di.loc[positive] = 100.0 * smoothed_plus.loc[positive] / smoothed_tr.loc[positive]
    minus_di.loc[positive] = 100.0 * smoothed_minus.loc[positive] / smoothed_tr.loc[positive]
    plus_di.loc[zero] = 0.0
    minus_di.loc[zero] = 0.0

    dx = pd.Series(np.nan, index=tr.index, dtype=float, name="dx")
    denominator = plus_di + minus_di
    di_ready = plus_di.notna() & minus_di.notna()
    dx.loc[di_ready & (denominator == 0)] = 0.0
    nonzero = di_ready & (denominator > 0)
    dx.loc[nonzero] = (
        100.0 * (plus_di.loc[nonzero] - minus_di.loc[nonzero]).abs() / denominator.loc[nonzero]
    )
    adx = wilder_smoothing(dx, period).rename("adx")
    return {
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "dx": dx,
        "true_range": tr,
    }


def _adx_state(value: float, weak_threshold: float, strong_threshold: float) -> str:
    if value < weak_threshold:
        return "weak_trend"
    if value < strong_threshold:
        return "developing_trend"
    return "strong_trend"


def _component(
    value: float | None,
    unit: IndicatorComponentUnit = "index",
    *,
    normalized_value: float | None = None,
) -> IndicatorComponent:
    """Construit une composante ADX éventuellement indisponible."""
    if value is None:
        return IndicatorComponent(
            value=None,
            normalized_value=None,
            unit=unit,
        )

    normalized = normalized_value

    if normalized is None:
        if unit == "index":
            normalized = value / 100.0
        elif unit == "ratio":
            normalized = value

    return IndicatorComponent(
        value=value,
        normalized_value=normalized,
        unit=unit,
    )


def _change(
    current: float,
    previous: float | None,
) -> float | None:
    """Retourne une variation causale lorsque la valeur précédente existe."""
    if previous is None:
        return None

    return current - previous


def build_adx_signal(
    data: dict[str, pd.Series],
    *,
    weak_threshold: float = 20,
    strong_threshold: float = 25,
) -> IndicatorSignal:
    """Construit le signal ADX/DMI ; les croisements ont priorité."""
    if not (
        math.isfinite(weak_threshold)
        and math.isfinite(strong_threshold)
        and 0 <= weak_threshold < strong_threshold <= 100
    ):
        return _unavailable_signal("invalid_data", "Seuils ADX invalides")
    frame = pd.concat(
        [
            data["adx"].rename("adx"),
            data["plus_di"].rename("plus_di"),
            data["minus_di"].rename("minus_di"),
            data["dx"].rename("dx"),
        ],
        axis=1,
    )
    if frame.empty:
        return _unavailable_signal("insufficient_data", "Historique ADX insuffisant")
    true_range = data.get("true_range")
    if true_range is not None and (
        true_range.empty or not math.isfinite(float(true_range.iloc[-1]))
    ):
        return _unavailable_signal("invalid_data", "Données OHLC invalides pour l'ADX")
    current = frame.iloc[-1]
    values = tuple(float(current[name]) for name in ("adx", "plus_di", "minus_di", "dx"))
    if not all(math.isfinite(value) for value in values):
        return _unavailable_signal("insufficient_data", "Historique ADX insuffisant")
    adx, plus_di, minus_di, dx = values
    direction: SignalDirection = (
        "bullish" if plus_di > minus_di else "bearish" if minus_di > plus_di else "neutral"
    )
    state = _adx_state(adx, weak_threshold, strong_threshold)

    di_spread = plus_di - minus_di
    di_total = plus_di + minus_di
    di_balance = 0.0 if abs(di_total) <= 1e-12 else di_spread / di_total

    previous_adx: float | None = None
    previous_plus: float | None = None
    previous_minus: float | None = None
    previous_dx: float | None = None

    if len(frame) >= 2:
        previous = frame.iloc[-2]
        candidate_values = (
            float(previous["adx"]),
            float(previous["plus_di"]),
            float(previous["minus_di"]),
            float(previous["dx"]),
        )

        if all(math.isfinite(value) for value in candidate_values):
            (
                previous_adx,
                previous_plus,
                previous_minus,
                previous_dx,
            ) = candidate_values

    previous_di_spread: float | None = None
    previous_di_balance: float | None = None

    if previous_plus is not None and previous_minus is not None:
        previous_di_spread = previous_plus - previous_minus
        previous_di_total = previous_plus + previous_minus

        previous_di_balance = (
            0.0 if abs(previous_di_total) <= 1e-12 else previous_di_spread / previous_di_total
        )

    event: str | None = None

    if previous_adx is not None and previous_plus is not None and previous_minus is not None:
        previous_state = _adx_state(
            previous_adx,
            weak_threshold,
            strong_threshold,
        )

        if previous_plus <= previous_minus and plus_di > minus_di:
            event = "bullish_cross"
        elif previous_plus >= previous_minus and minus_di > plus_di:
            event = "bearish_cross"
        elif previous_state != "strong_trend" and state == "strong_trend":
            event = "trend_strengthening"
        elif previous_state == "strong_trend" and state != "strong_trend":
            event = "trend_weakening"

    adx_change = _change(
        adx,
        previous_adx,
    )
    plus_di_change = _change(
        plus_di,
        previous_plus,
    )
    minus_di_change = _change(
        minus_di,
        previous_minus,
    )
    dx_change = _change(
        dx,
        previous_dx,
    )
    di_spread_change = _change(
        di_spread,
        previous_di_spread,
    )

    components = {
        "adx": _component(adx),
        "plus_di": _component(plus_di),
        "minus_di": _component(minus_di),
        "dx": _component(dx),
        "di_spread": _component(di_spread),
        "di_balance": _component(
            di_balance,
            "ratio",
            normalized_value=di_balance,
        ),
        "previous_adx": _component(previous_adx),
        "previous_plus_di": _component(previous_plus),
        "previous_minus_di": _component(previous_minus),
        "previous_dx": _component(previous_dx),
        "previous_di_spread": _component(
            previous_di_spread,
        ),
        "previous_di_balance": _component(
            previous_di_balance,
            "ratio",
            normalized_value=previous_di_balance,
        ),
        "adx_change": _component(adx_change),
        "plus_di_change": _component(plus_di_change),
        "minus_di_change": _component(minus_di_change),
        "dx_change": _component(dx_change),
        "di_spread_change": _component(di_spread_change),
        "distance_from_weak_threshold": _component(
            adx - weak_threshold,
        ),
        "distance_from_strong_threshold": _component(
            adx - strong_threshold,
        ),
    }

    return IndicatorSignal(
        status="available",
        direction=direction,
        signal=event,
        state=state,
        strength=_clamp_strength(adx / 50.0),
        reason=f"ADX {state}, +DI {plus_di:.2f}, -DI {minus_di:.2f}",
        raw_value=adx,
        components=components,
    )


def detect_adx_events(
    data: dict[str, pd.Series] | None,
    *,
    weak_threshold: float = 20,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les croisements DMI confirmés par une force ADX suffisante.

    Un événement haussier est produit lorsque +DI croise au-dessus de -DI
    et que l'ADX courant est supérieur ou égal au seuil faible.

    Un événement baissier est produit lorsque -DI croise au-dessus de +DI
    avec la même condition de force.

    Les croisements lorsque l'ADX est inférieur au seuil sont ignorés afin
    de réduire les signaux produits dans les marchés sans tendance.
    """
    if data is None:
        return []

    required = {
        "adx",
        "plus_di",
        "minus_di",
    }
    if not required <= set(data):
        return []

    if not math.isfinite(weak_threshold) or not 0 <= weak_threshold <= 100:
        return []

    frame_columns = [
        data["adx"].astype(float).rename("adx"),
        data["plus_di"].astype(float).rename("plus_di"),
        data["minus_di"].astype(float).rename("minus_di"),
    ]

    true_range = data.get("true_range")
    if true_range is not None:
        frame_columns.append(true_range.astype(float).rename("true_range"))

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
            previous["plus_di"],
            previous["minus_di"],
            current["adx"],
            current["plus_di"],
            current["minus_di"],
        )

        if any(pd.isna(value) for value in raw_values):
            continue

        previous_plus = float(previous["plus_di"])
        previous_minus = float(previous["minus_di"])
        current_adx = float(current["adx"])
        current_plus = float(current["plus_di"])
        current_minus = float(current["minus_di"])

        numeric_values = (
            previous_plus,
            previous_minus,
            current_adx,
            current_plus,
            current_minus,
        )

        if not all(math.isfinite(value) for value in numeric_values):
            continue

        if "true_range" in frame.columns:
            current_true_range = current["true_range"]

            if pd.isna(current_true_range):
                continue

            if not math.isfinite(float(current_true_range)):
                continue

        # Le croisement est ignoré lorsque la tendance est trop faible.
        if current_adx < weak_threshold:
            continue

        bullish_cross = previous_plus <= previous_minus and current_plus > current_minus
        bearish_cross = previous_plus >= previous_minus and current_minus > current_plus

        strength = _clamp_strength(current_adx / 50.0)

        if bullish_cross:
            events.append(
                IndicatorEvent(
                    indicator="adx",
                    position=position,
                    direction="bullish",
                    event="bullish_cross",
                    kind="cross",
                    strength=strength,
                    metadata={
                        "previous_plus_di": previous_plus,
                        "previous_minus_di": previous_minus,
                        "current_plus_di": current_plus,
                        "current_minus_di": current_minus,
                        "current_adx": current_adx,
                        "weak_threshold": weak_threshold,
                    },
                )
            )

        elif bearish_cross:
            events.append(
                IndicatorEvent(
                    indicator="adx",
                    position=position,
                    direction="bearish",
                    event="bearish_cross",
                    kind="cross",
                    strength=strength,
                    metadata={
                        "previous_plus_di": previous_plus,
                        "previous_minus_di": previous_minus,
                        "current_plus_di": current_plus,
                        "current_minus_di": current_minus,
                        "current_adx": current_adx,
                        "weak_threshold": weak_threshold,
                    },
                )
            )

    return events
