"""Supertrend causal fondé sur l'ATR de Wilder."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.atr import calculate_atr
from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorEvent,
    IndicatorSignal,
    SignalDirection,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "build_supertrend_signal",
    "calculate_supertrend",
    "detect_supertrend_events",
]


def calculate_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int = 10,
    multiplier: float = 3.0,
    *,
    atr: pd.Series | None = None,
) -> dict[str, pd.Series]:
    """Calcule les bandes finales et le régime Supertrend sans donnée future.

    À la première valeur ATR, le régime est initialisé d'après ``close >= hl2``.
    Les bandes finales suivent ensuite les règles utilisant seulement la bande
    et le close précédents.
    """
    if isinstance(atr_period, bool) or not isinstance(atr_period, int) or atr_period < 1:
        raise ValueError("atr_period doit être un entier supérieur ou égal à 1")
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("multiplier doit être fini et strictement positif")
    frame = pd.concat(
        [
            high.astype(float).rename("high"),
            low.astype(float).rename("low"),
            close.astype(float).rename("close"),
        ],
        axis=1,
    )
    atr_series = (
        atr.astype(float)
        if atr is not None
        else calculate_atr(frame["high"], frame["low"], frame["close"], atr_period)["atr"]
    )
    hl2 = (frame["high"] + frame["low"]) / 2.0
    basic_upper = hl2 + multiplier * atr_series
    basic_lower = hl2 - multiplier * atr_series
    upper = pd.Series(np.nan, index=frame.index, dtype=float, name="upper_band")
    lower = pd.Series(np.nan, index=frame.index, dtype=float, name="lower_band")
    trend = pd.Series(np.nan, index=frame.index, dtype=float, name="trend")
    line = pd.Series(np.nan, index=frame.index, dtype=float, name="supertrend")
    input_valid = pd.Series(False, index=frame.index, dtype=bool, name="input_valid")

    previous_index: object | None = None
    for index in frame.index:
        current_values = (
            float(frame.loc[index, "high"]),
            float(frame.loc[index, "low"]),
            float(frame.loc[index, "close"]),
            float(atr_series.loc[index]),
            float(basic_upper.loc[index]),
            float(basic_lower.loc[index]),
        )
        valid = (
            all(math.isfinite(value) for value in current_values)
            and current_values[0] >= current_values[1] > 0
            and current_values[2] > 0
        )
        if not valid:
            previous_index = None
            continue
        input_valid.loc[index] = True
        current_close = current_values[2]
        if previous_index is None:
            upper.loc[index] = current_values[4]
            lower.loc[index] = current_values[5]
            bullish = current_close >= float(hl2.loc[index])
        else:
            previous_close = float(frame.loc[previous_index, "close"])
            previous_upper = float(upper.loc[previous_index])
            previous_lower = float(lower.loc[previous_index])
            upper.loc[index] = (
                current_values[4]
                if current_values[4] < previous_upper or previous_close > previous_upper
                else previous_upper
            )
            lower.loc[index] = (
                current_values[5]
                if current_values[5] > previous_lower or previous_close < previous_lower
                else previous_lower
            )
            was_bullish = bool(trend.loc[previous_index] > 0)
            if was_bullish:
                bullish = not (current_close < float(lower.loc[index]))
            else:
                bullish = current_close > float(upper.loc[index])
        trend.loc[index] = 1.0 if bullish else -1.0
        line.loc[index] = float(lower.loc[index] if bullish else upper.loc[index])
        previous_index = index

    return {
        "supertrend": line,
        "upper_band": upper,
        "lower_band": lower,
        "atr": atr_series.rename("atr"),
        "trend": trend,
        "input_valid": input_valid,
    }


def detect_supertrend_events(
    data: dict[str, pd.Series],
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les changements confirmés de régime Supertrend.

    La fonction ne produit un événement que lorsque deux positions
    consécutives et valides passent d'un régime baissier à haussier,
    ou inversement.

    Args:
        data: Résultat retourné par :func:`calculate_supertrend`.
        only_last: Lorsque vrai, ne vérifie que la dernière position.

    Returns:
        Les événements Supertrend ordonnés chronologiquement.
    """
    trend = data.get("trend")
    if trend is None or len(trend) < 2:
        return []

    input_valid = data.get("input_valid")
    if input_valid is not None and len(input_valid) != len(trend):
        return []

    start_position = len(trend) - 1 if only_last else 1
    events: list[IndicatorEvent] = []

    for position in range(start_position, len(trend)):
        previous_position = position - 1

        if input_valid is not None:
            previous_valid = bool(input_valid.iloc[previous_position])
            current_valid = bool(input_valid.iloc[position])

            # Ne pas comparer deux régimes séparés par une donnée invalide.
            if not previous_valid or not current_valid:
                continue

        previous_trend = float(trend.iloc[previous_position])
        current_trend = float(trend.iloc[position])

        if not math.isfinite(previous_trend):
            continue

        if not math.isfinite(current_trend):
            continue

        previous_bullish = previous_trend > 0
        current_bullish = current_trend > 0

        if previous_bullish == current_bullish:
            continue

        bullish = current_bullish

        events.append(
            IndicatorEvent(
                indicator="supertrend",
                position=position,
                direction="bullish" if bullish else "bearish",
                event="bullish_flip" if bullish else "bearish_flip",
                kind="trend_change",
                metadata={
                    "previous_trend": previous_trend,
                    "current_trend": current_trend,
                },
            )
        )

    return events


def _price_component(
    value: float | None,
    *,
    normalized_value: float | None = None,
) -> IndicatorComponent:
    """Construit une composante exprimée en prix."""
    return IndicatorComponent(
        value=value,
        normalized_value=(normalized_value if value is not None else None),
        unit="price",
    )


def _relative_distance(
    first: float,
    second: float,
) -> float:
    """Normalise une distance signée entre deux valeurs."""
    denominator = abs(first) + abs(second)

    if denominator <= 1e-12:
        return 0.0

    return (first - second) / denominator


def build_supertrend_signal(
    data: dict[str, pd.Series],
    close: pd.Series,
) -> IndicatorSignal:
    """Construit l'état persistant et n'émet un flip qu'au changement de régime."""
    if close.empty:
        return _unavailable_signal("insufficient_data", "Historique Supertrend insuffisant")
    current_close = float(close.iloc[-1])
    if not math.isfinite(current_close) or current_close <= 0:
        return _unavailable_signal("invalid_data", "Close invalide pour Supertrend")
    input_valid = data.get("input_valid")
    if input_valid is not None and (input_valid.empty or not bool(input_valid.iloc[-1])):
        return _unavailable_signal("invalid_data", "Données OHLC invalides pour Supertrend")
    current = {
        name: float(data[name].iloc[-1])
        for name in ("supertrend", "upper_band", "lower_band", "atr", "trend")
    }
    if not all(math.isfinite(value) for value in current.values()):
        return _unavailable_signal("insufficient_data", "Historique Supertrend insuffisant")
    if current["atr"] < 0:
        return _unavailable_signal("invalid_data", "ATR invalide pour Supertrend")

    bullish = current["trend"] > 0
    direction: SignalDirection = "bullish" if bullish else "bearish"
    state = "uptrend" if bullish else "downtrend"

    previous_close: float | None = None
    previous_supertrend: float | None = None
    previous_upper: float | None = None
    previous_lower: float | None = None
    previous_atr: float | None = None
    previous_trend: float | None = None

    previous_input_valid = True

    if input_valid is not None and len(input_valid) >= 2:
        previous_input_valid = bool(input_valid.iloc[-2])

    if len(close) >= 2 and previous_input_valid:
        candidate_previous = {
            "close": float(close.iloc[-2]),
            "supertrend": float(data["supertrend"].iloc[-2]),
            "upper_band": float(data["upper_band"].iloc[-2]),
            "lower_band": float(data["lower_band"].iloc[-2]),
            "atr": float(data["atr"].iloc[-2]),
            "trend": float(data["trend"].iloc[-2]),
        }

        if (
            all(math.isfinite(value) for value in candidate_previous.values())
            and candidate_previous["close"] > 0
            and candidate_previous["atr"] >= 0
        ):
            previous_close = candidate_previous["close"]
            previous_supertrend = candidate_previous["supertrend"]
            previous_upper = candidate_previous["upper_band"]
            previous_lower = candidate_previous["lower_band"]
            previous_atr = candidate_previous["atr"]
            previous_trend = candidate_previous["trend"]

    event: str | None = None

    if previous_trend is not None:
        previous_bullish = previous_trend > 0

        if previous_bullish != bullish:
            event = "bullish_flip" if bullish else "bearish_flip"

    price_to_supertrend = current_close - current["supertrend"]
    distance_ratio = price_to_supertrend / current_close
    distance_atr = price_to_supertrend / max(
        current["atr"],
        1e-12,
    )

    band_width = current["upper_band"] - current["lower_band"]
    band_position = (
        0.5 if abs(band_width) <= 1e-12 else (current_close - current["lower_band"]) / band_width
    )

    previous_distance_ratio: float | None = None
    previous_distance_atr: float | None = None
    previous_band_width: float | None = None
    previous_band_position: float | None = None

    if (
        previous_close is not None
        and previous_supertrend is not None
        and previous_upper is not None
        and previous_lower is not None
        and previous_atr is not None
    ):
        previous_price_to_supertrend = previous_close - previous_supertrend
        previous_distance_ratio = previous_price_to_supertrend / previous_close
        previous_distance_atr = previous_price_to_supertrend / max(
            previous_atr,
            1e-12,
        )

        previous_band_width = previous_upper - previous_lower
        previous_band_position = (
            0.5
            if abs(previous_band_width) <= 1e-12
            else (previous_close - previous_lower) / previous_band_width
        )

    supertrend_change = (
        current["supertrend"] - previous_supertrend if previous_supertrend is not None else None
    )
    upper_band_change = (
        current["upper_band"] - previous_upper if previous_upper is not None else None
    )
    lower_band_change = (
        current["lower_band"] - previous_lower if previous_lower is not None else None
    )
    atr_change = current["atr"] - previous_atr if previous_atr is not None else None
    band_width_change = (
        band_width - previous_band_width if previous_band_width is not None else None
    )
    distance_ratio_change = (
        distance_ratio - previous_distance_ratio if previous_distance_ratio is not None else None
    )
    distance_atr_change = (
        distance_atr - previous_distance_atr if previous_distance_atr is not None else None
    )
    band_position_change = (
        band_position - previous_band_position if previous_band_position is not None else None
    )

    components = {
        "supertrend": _price_component(
            current["supertrend"],
            normalized_value=(current["supertrend"] / current_close),
        ),
        "upper_band": _price_component(
            current["upper_band"],
            normalized_value=(current["upper_band"] / current_close),
        ),
        "lower_band": _price_component(
            current["lower_band"],
            normalized_value=(current["lower_band"] / current_close),
        ),
        "atr": _price_component(
            current["atr"],
            normalized_value=(current["atr"] / current_close),
        ),
        "price_to_supertrend_distance": _price_component(
            price_to_supertrend,
            normalized_value=distance_ratio,
        ),
        "price_to_upper_distance": _price_component(
            current_close - current["upper_band"],
            normalized_value=_relative_distance(
                current_close,
                current["upper_band"],
            ),
        ),
        "price_to_lower_distance": _price_component(
            current_close - current["lower_band"],
            normalized_value=_relative_distance(
                current_close,
                current["lower_band"],
            ),
        ),
        "distance_ratio": IndicatorComponent(
            value=distance_ratio,
            normalized_value=distance_ratio,
            unit="ratio",
        ),
        "distance_atr": IndicatorComponent(
            value=distance_atr,
            normalized_value=distance_atr,
            unit="ratio",
        ),
        "band_width": _price_component(
            band_width,
            normalized_value=(band_width / current_close),
        ),
        "band_position": IndicatorComponent(
            value=band_position,
            normalized_value=band_position,
            unit="ratio",
        ),
        "previous_supertrend": _price_component(
            previous_supertrend,
            normalized_value=(
                previous_supertrend / previous_close
                if (previous_supertrend is not None and previous_close is not None)
                else None
            ),
        ),
        "previous_upper_band": _price_component(
            previous_upper,
            normalized_value=(
                previous_upper / previous_close
                if (previous_upper is not None and previous_close is not None)
                else None
            ),
        ),
        "previous_lower_band": _price_component(
            previous_lower,
            normalized_value=(
                previous_lower / previous_close
                if (previous_lower is not None and previous_close is not None)
                else None
            ),
        ),
        "previous_atr": _price_component(
            previous_atr,
            normalized_value=(
                previous_atr / previous_close
                if (previous_atr is not None and previous_close is not None)
                else None
            ),
        ),
        "previous_distance_ratio": IndicatorComponent(
            value=previous_distance_ratio,
            normalized_value=previous_distance_ratio,
            unit="ratio",
        ),
        "previous_distance_atr": IndicatorComponent(
            value=previous_distance_atr,
            normalized_value=previous_distance_atr,
            unit="ratio",
        ),
        "previous_band_width": _price_component(
            previous_band_width,
            normalized_value=(
                previous_band_width / previous_close
                if (previous_band_width is not None and previous_close is not None)
                else None
            ),
        ),
        "previous_band_position": IndicatorComponent(
            value=previous_band_position,
            normalized_value=previous_band_position,
            unit="ratio",
        ),
        "supertrend_change": _price_component(
            supertrend_change,
            normalized_value=(
                _relative_distance(
                    current["supertrend"],
                    previous_supertrend,
                )
                if previous_supertrend is not None
                else None
            ),
        ),
        "upper_band_change": _price_component(
            upper_band_change,
            normalized_value=(
                _relative_distance(
                    current["upper_band"],
                    previous_upper,
                )
                if previous_upper is not None
                else None
            ),
        ),
        "lower_band_change": _price_component(
            lower_band_change,
            normalized_value=(
                _relative_distance(
                    current["lower_band"],
                    previous_lower,
                )
                if previous_lower is not None
                else None
            ),
        ),
        "atr_change": _price_component(
            atr_change,
            normalized_value=(
                _relative_distance(
                    current["atr"],
                    previous_atr,
                )
                if previous_atr is not None
                else None
            ),
        ),
        "band_width_change": _price_component(
            band_width_change,
            normalized_value=(
                _relative_distance(
                    band_width,
                    previous_band_width,
                )
                if previous_band_width is not None
                else None
            ),
        ),
        "distance_ratio_change": IndicatorComponent(
            value=distance_ratio_change,
            normalized_value=distance_ratio_change,
            unit="ratio",
        ),
        "distance_atr_change": IndicatorComponent(
            value=distance_atr_change,
            normalized_value=distance_atr_change,
            unit="ratio",
        ),
        "band_position_change": IndicatorComponent(
            value=band_position_change,
            normalized_value=band_position_change,
            unit="ratio",
        ),
    }

    return IndicatorSignal(
        status="available",
        direction=direction,
        signal=event,
        state=state,
        strength=_clamp_strength(abs(distance_atr)),
        reason=f"Supertrend {state}",
        raw_value=current["supertrend"],
        components=components,
    )
