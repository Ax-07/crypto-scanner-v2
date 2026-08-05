"""ATR/NATR de Wilder et signal structuré de volatilité."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.domain.indicators.types import (
    IndicatorComponent,
    IndicatorComponentUnit,
    IndicatorEvent,
    IndicatorSignal,
    _clamp_strength,
    _unavailable_signal,
)
from app.domain.indicators.wilder import calculate_true_range, wilder_smoothing

__all__ = [
    "build_atr_signal",
    "calculate_atr",
    "calculate_natr",
    "detect_atr_events",
]


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    *,
    true_range: pd.Series | None = None,
) -> dict[str, pd.Series]:
    """Calcule TR et ATR avec une SMA d'amorçage puis le lissage de Wilder."""
    tr = true_range if true_range is not None else calculate_true_range(high, low, close)
    return {"true_range": tr.copy(), "atr": wilder_smoothing(tr, period)}


def calculate_natr(atr: pd.Series, close: pd.Series) -> pd.Series:
    """Retourne ``100 * ATR / close`` : la valeur publique est un pourcentage."""
    aligned = pd.concat(
        [atr.astype(float).rename("atr"), close.astype(float).rename("close")],
        axis=1,
    )
    valid = np.isfinite(aligned["atr"]) & np.isfinite(aligned["close"]) & (aligned["close"] > 0)
    result = pd.Series(np.nan, index=aligned.index, dtype=float, name="natr")
    result.loc[valid] = 100.0 * aligned.loc[valid, "atr"] / aligned.loc[valid, "close"]
    return result


def _volatility_state(previous: float, current: float) -> str:
    if math.isclose(current, previous, rel_tol=1e-12, abs_tol=1e-12):
        return "stable"
    return "expanding" if current > previous else "contracting"


def _component(
    value: float | None,
    unit: IndicatorComponentUnit,
    *,
    normalized_value: float | None = None,
) -> IndicatorComponent:
    return IndicatorComponent(
        value=value,
        normalized_value=normalized_value,
        unit=unit,
    )


def _finite_series_value(
    series: pd.Series,
    position: int,
) -> float | None:
    """Retourne une valeur finie d'une série, si elle existe."""
    try:
        value = float(series.iloc[position])
    except IndexError:
        return None

    return value if math.isfinite(value) else None


def _price_normalized_value(
    value: float | None,
    close_value: float | None,
) -> float | None:
    """Normalise une valeur exprimée en prix par la clôture correspondante."""
    if value is None or close_value is None or not math.isfinite(close_value) or close_value <= 0:
        return None

    return value / close_value


def build_atr_signal(
    data: dict[str, pd.Series],
    close: pd.Series,
) -> IndicatorSignal:
    """Construit le signal ATR/NATR sans jamais lui donner un biais de prix."""
    if close.empty:
        return _unavailable_signal("insufficient_data", "Historique ATR insuffisant")
    current_close = float(close.iloc[-1])
    if not math.isfinite(current_close) or current_close <= 0:
        return _unavailable_signal("invalid_data", "Close invalide pour le NATR")

    tr = data["true_range"]
    atr = data["atr"]
    natr = data.get("natr")
    if natr is None:
        natr = calculate_natr(atr, close)
    current_values = (float(tr.iloc[-1]), float(atr.iloc[-1]), float(natr.iloc[-1]))
    if not math.isfinite(current_values[0]):
        return _unavailable_signal("invalid_data", "Données OHLC invalides pour le True Range")
    if not all(math.isfinite(value) for value in current_values[1:]):
        return _unavailable_signal("insufficient_data", "Historique ATR insuffisant")

    valid_natr = natr.iloc[:0]
    for start in range(len(natr) - 1, -1, -1):
        if not math.isfinite(float(natr.iloc[start])):
            valid_natr = natr.iloc[start + 1 :]
            break
    else:
        valid_natr = natr
    if len(valid_natr) < 2:
        return _unavailable_signal("insufficient_data", "Deux valeurs NATR sont requises")
    previous_natr = float(valid_natr.iloc[-2])
    current_natr = float(valid_natr.iloc[-1])
    change = current_natr - previous_natr

    state = _volatility_state(
        previous_natr,
        current_natr,
    )

    event: str | None = None

    if len(valid_natr) >= 3:
        previous_state = _volatility_state(
            float(valid_natr.iloc[-3]),
            previous_natr,
        )

        if state != previous_state:
            event = {
                "expanding": "volatility_expansion",
                "contracting": "volatility_contraction",
                "stable": "volatility_stable",
            }[state]

    signed_relative_change = change / max(
        abs(previous_natr),
        1e-12,
    )
    relative_change = abs(signed_relative_change)

    current_true_range = current_values[0]
    current_atr = current_values[1]

    previous_close = _finite_series_value(
        close,
        -2,
    )
    previous_true_range = _finite_series_value(
        tr,
        -2,
    )
    previous_atr = _finite_series_value(
        atr,
        -2,
    )

    true_range_change = (
        current_true_range - previous_true_range if previous_true_range is not None else None
    )
    atr_change = current_atr - previous_atr if previous_atr is not None else None

    components = {
        "true_range": _component(
            current_true_range,
            "price",
            normalized_value=_price_normalized_value(
                current_true_range,
                current_close,
            ),
        ),
        "atr": _component(
            current_atr,
            "price",
            normalized_value=_price_normalized_value(
                current_atr,
                current_close,
            ),
        ),
        "natr": _component(
            current_natr,
            "percent",
            normalized_value=current_natr / 100.0,
        ),
        "previous_true_range": _component(
            previous_true_range,
            "price",
            normalized_value=_price_normalized_value(
                previous_true_range,
                previous_close,
            ),
        ),
        "previous_atr": _component(
            previous_atr,
            "price",
            normalized_value=_price_normalized_value(
                previous_atr,
                previous_close,
            ),
        ),
        "previous_natr": _component(
            previous_natr,
            "percent",
            normalized_value=previous_natr / 100.0,
        ),
        "true_range_change": _component(
            true_range_change,
            "price",
            normalized_value=_price_normalized_value(
                true_range_change,
                current_close,
            ),
        ),
        "atr_change": _component(
            atr_change,
            "price",
            normalized_value=_price_normalized_value(
                atr_change,
                current_close,
            ),
        ),
        "natr_change": _component(
            change,
            "percent",
            normalized_value=change / 100.0,
        ),
        "relative_natr_change": _component(
            signed_relative_change,
            "ratio",
            normalized_value=signed_relative_change,
        ),
    }
    return IndicatorSignal(
        status="available",
        direction="neutral",
        signal=event,
        state=state,
        strength=_clamp_strength(relative_change),
        reason=f"NATR {state} ({current_natr:.4f} %)",
        raw_value=current_natr,
        components=components,
    )


def detect_atr_events(
    data: dict[str, pd.Series] | None,
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les changements de régime de volatilité du NATR.

    Une expansion est produite lorsque le NATR commence à augmenter après
    une phase stable ou décroissante.

    Une contraction est produite lorsque le NATR commence à diminuer après
    une phase stable ou croissante.

    Les périodes restant durablement dans le même régime ne produisent pas
    de nouvel événement. Les transitions vers un état stable sont également
    ignorées afin de ne pas surcharger le graphique.
    """
    if data is None:
        return []

    natr = data.get("natr")
    if natr is None:
        return []

    values = pd.to_numeric(
        natr.reset_index(drop=True),
        errors="coerce",
    )

    # Trois valeurs sont nécessaires :
    # t-2 -> t-1 pour le régime précédent,
    # t-1 -> t pour le régime courant.
    if len(values) < 3:
        return []

    start_position = len(values) - 1 if only_last else 2
    events: list[IndicatorEvent] = []

    for position in range(start_position, len(values)):
        before_previous_raw = values.iloc[position - 2]
        previous_raw = values.iloc[position - 1]
        current_raw = values.iloc[position]

        raw_values = (
            before_previous_raw,
            previous_raw,
            current_raw,
        )

        if any(pd.isna(value) for value in raw_values):
            continue

        before_previous = float(before_previous_raw)
        previous = float(previous_raw)
        current = float(current_raw)

        if not all(
            math.isfinite(value)
            for value in (
                before_previous,
                previous,
                current,
            )
        ):
            continue

        if before_previous < 0 or previous < 0 or current < 0:
            continue

        previous_state = _volatility_state(
            before_previous,
            previous,
        )
        current_state = _volatility_state(
            previous,
            current,
        )

        # Aucun événement lorsque le régime ne change pas.
        if current_state == previous_state:
            continue

        # Le retour vers un état stable est volontairement ignoré.
        if current_state == "stable":
            continue

        change = current - previous
        relative_change = abs(change) / max(abs(previous), 1e-12)
        strength = _clamp_strength(relative_change)

        if current_state == "expanding":
            events.append(
                IndicatorEvent(
                    indicator="atr",
                    position=position,
                    direction="neutral",
                    event="volatility_expansion",
                    kind="volatility_regime",
                    strength=strength,
                    metadata={
                        "before_previous_natr": before_previous,
                        "previous_natr": previous,
                        "current_natr": current,
                        "previous_state": previous_state,
                        "current_state": current_state,
                        "natr_change": change,
                        "relative_change": relative_change,
                    },
                )
            )

        elif current_state == "contracting":
            events.append(
                IndicatorEvent(
                    indicator="atr",
                    position=position,
                    direction="neutral",
                    event="volatility_contraction",
                    kind="volatility_regime",
                    strength=strength,
                    metadata={
                        "before_previous_natr": before_previous,
                        "previous_natr": previous,
                        "current_natr": current,
                        "previous_state": previous_state,
                        "current_state": current_state,
                        "natr_change": change,
                        "relative_change": relative_change,
                    },
                )
            )

    return events
