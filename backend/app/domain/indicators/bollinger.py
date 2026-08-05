"""Bandes de Bollinger, classification de position et signal structuré."""

from __future__ import annotations

import math

import pandas as pd

from app.domain.indicators.moving_averages import calculate_sma
from app.domain.indicators.types import (
    BollingerPosition,
    IndicatorComponent,
    IndicatorEvent,
    IndicatorSignal,
    SignalDirection,
    _clamp_strength,
    _unavailable_signal,
)

__all__ = [
    "calculate_bollinger_bands",
    "calculate_bollinger_band_width",
    "detect_bollinger_events",
    "detect_bollinger_signal",
    "is_bollinger_degenerate",
    "build_bollinger_signal",
]


def calculate_bollinger_band_width(
    close: pd.Series,
    bands: dict[str, pd.Series],
) -> dict[str, pd.Series]:
    """Dérive largeur et position des bandes déjà calculées, sans les recalculer."""
    frame = pd.concat(
        [
            close.astype(float).rename("close"),
            bands["upper"].astype(float).rename("upper"),
            bands["middle"].astype(float).rename("middle"),
            bands["lower"].astype(float).rename("lower"),
        ],
        axis=1,
    )
    width = (frame["upper"] - frame["lower"]).rename("band_width")
    width_percent = pd.Series(float("nan"), index=frame.index, dtype=float)
    valid_middle = frame["middle"].map(math.isfinite) & (frame["middle"] > 0)
    width_percent.loc[valid_middle] = (
        100.0 * width.loc[valid_middle] / frame.loc[valid_middle, "middle"]
    )
    position = pd.Series(float("nan"), index=frame.index, dtype=float)
    positive_width = width.map(math.isfinite) & (width > 0)
    position.loc[positive_width] = (
        frame.loc[positive_width, "close"] - frame.loc[positive_width, "lower"]
    ) / width.loc[positive_width]
    constant = width.map(math.isfinite) & (width.abs() <= 1e-12)
    position.loc[constant] = 0.5
    return {
        "middle_band": frame["middle"],
        "upper_band": frame["upper"],
        "lower_band": frame["lower"],
        "band_width": width,
        "band_width_percent": width_percent.rename("band_width_percent"),
        "band_position": position.rename("band_position"),
    }


def _normalized_price_distance(
    first: float,
    second: float,
) -> float:
    """Normalise une distance signée entre deux niveaux de prix."""
    denominator = abs(first) + abs(second)

    if denominator <= 1e-12:
        return 0.0

    return (first - second) / denominator


def _bollinger_components(
    close: pd.Series,
    bands: dict[str, pd.Series],
) -> dict[str, IndicatorComponent] | None:
    """Construit les composantes continues et causales de Bollinger."""
    if not {"upper", "middle", "lower"} <= set(bands):
        return None

    derived = calculate_bollinger_band_width(close, bands)

    frame = pd.concat(
        [
            close.astype(float).rename("close"),
            *[series.astype(float).rename(name) for name, series in derived.items()],
        ],
        axis=1,
    )

    if frame.empty:
        return None

    current = frame.iloc[-1]
    current_values = {
        name: float(current[name])
        for name in (
            "close",
            "middle_band",
            "upper_band",
            "lower_band",
            "band_width",
            "band_width_percent",
            "band_position",
        )
    }

    if not all(math.isfinite(value) for value in current_values.values()):
        return None

    previous_middle: float | None = None
    previous_width_percent: float | None = None
    previous_position: float | None = None

    if len(frame) >= 2:
        previous = frame.iloc[-2]

        candidate_previous_middle = float(previous["middle_band"])
        candidate_previous_width_percent = float(previous["band_width_percent"])
        candidate_previous_position = float(previous["band_position"])

        if all(
            math.isfinite(value)
            for value in (
                candidate_previous_middle,
                candidate_previous_width_percent,
                candidate_previous_position,
            )
        ):
            previous_middle = candidate_previous_middle
            previous_width_percent = candidate_previous_width_percent
            previous_position = candidate_previous_position

    current_close = current_values["close"]
    current_middle = current_values["middle_band"]
    current_upper = current_values["upper_band"]
    current_lower = current_values["lower_band"]
    current_width = current_values["band_width"]
    current_width_percent = current_values["band_width_percent"]
    current_position = current_values["band_position"]

    width_percent_change = (
        current_width_percent - previous_width_percent
        if previous_width_percent is not None
        else None
    )
    position_change = (
        current_position - previous_position if previous_position is not None else None
    )
    middle_change = current_middle - previous_middle if previous_middle is not None else None

    normalized_middle_change = (
        _normalized_price_distance(
            current_middle,
            previous_middle,
        )
        if previous_middle is not None
        else None
    )

    normalized_close_denominator = abs(current_close)

    return {
        "middle_band": IndicatorComponent(
            value=current_middle,
            normalized_value=(
                current_middle / current_close if normalized_close_denominator > 1e-12 else None
            ),
            unit="price",
        ),
        "upper_band": IndicatorComponent(
            value=current_upper,
            normalized_value=(
                current_upper / current_close if normalized_close_denominator > 1e-12 else None
            ),
            unit="price",
        ),
        "lower_band": IndicatorComponent(
            value=current_lower,
            normalized_value=(
                current_lower / current_close if normalized_close_denominator > 1e-12 else None
            ),
            unit="price",
        ),
        "band_width": IndicatorComponent(
            value=current_width,
            normalized_value=(
                current_width / normalized_close_denominator
                if normalized_close_denominator > 1e-12
                else None
            ),
            unit="price",
        ),
        "band_width_percent": IndicatorComponent(
            value=current_width_percent,
            normalized_value=current_width_percent / 100.0,
            unit="percent",
        ),
        "band_position": IndicatorComponent(
            value=current_position,
            normalized_value=current_position,
            unit="ratio",
        ),
        "price_to_middle_distance": IndicatorComponent(
            value=current_close - current_middle,
            normalized_value=_normalized_price_distance(
                current_close,
                current_middle,
            ),
            unit="price",
        ),
        "price_to_upper_distance": IndicatorComponent(
            value=current_close - current_upper,
            normalized_value=_normalized_price_distance(
                current_close,
                current_upper,
            ),
            unit="price",
        ),
        "price_to_lower_distance": IndicatorComponent(
            value=current_close - current_lower,
            normalized_value=_normalized_price_distance(
                current_close,
                current_lower,
            ),
            unit="price",
        ),
        "previous_band_width_percent": IndicatorComponent(
            value=previous_width_percent,
            normalized_value=(
                previous_width_percent / 100.0 if previous_width_percent is not None else None
            ),
            unit="percent",
        ),
        "previous_band_position": IndicatorComponent(
            value=previous_position,
            normalized_value=previous_position,
            unit="ratio",
        ),
        "band_width_percent_change": IndicatorComponent(
            value=width_percent_change,
            normalized_value=(
                width_percent_change / 100.0 if width_percent_change is not None else None
            ),
            unit="percent",
        ),
        "band_position_change": IndicatorComponent(
            value=position_change,
            normalized_value=position_change,
            unit="ratio",
        ),
        "middle_band_change": IndicatorComponent(
            value=middle_change,
            normalized_value=normalized_middle_change,
            unit="price",
        ),
    }


def calculate_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> dict[str, pd.Series]:
    """Calcule les bandes de Bollinger avec écart-type de population."""
    middle = calculate_sma(close, period)
    deviation = close.astype(float).rolling(period, min_periods=period).std(ddof=0)
    return {
        "upper": middle + deviation * std_dev,
        "middle": middle,
        "lower": middle - deviation * std_dev,
    }


def _classify_position(
    close_value: float, upper_value: float, lower_value: float
) -> BollingerPosition:
    """Classe une position de prix ponctuelle entre les bandes de Bollinger.

    Factorise la règle utilisée par :func:`detect_bollinger_signal` et
    :func:`build_bollinger_signal` afin d'éviter toute duplication.
    """
    width = upper_value - lower_value
    if width <= 1e-12 or width / max(abs(close_value), 1e-12) <= 1e-10:
        return "neutral"
    position = (close_value - lower_value) / width
    if position <= 0:
        return "oversold"
    if position <= 0.15:
        return "near_oversold"
    if position >= 1:
        return "overbought"
    if position >= 0.85:
        return "near_overbought"
    return "neutral"


def detect_bollinger_events(
    close: pd.Series | None,
    bands: dict[str, pd.Series] | None,
    *,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Détecte les réintégrations ponctuelles des bandes de Bollinger.

    Une réintégration de la bande basse est haussière lorsque la clôture
    précédente se trouvait sous ou sur la bande basse et que la clôture
    courante repasse au-dessus de sa bande basse.

    Une réintégration de la bande haute est baissière lorsque la clôture
    précédente se trouvait au-dessus ou sur la bande haute et que la clôture
    courante repasse sous sa bande haute.

    Les positions restent alignées sur les bougies OHLCV d'origine.
    """
    if close is None or bands is None:
        return []

    if not {"upper", "lower"} <= set(bands):
        return []

    frame = pd.concat(
        [
            close.astype(float).rename("close"),
            bands["upper"].astype(float).rename("upper"),
            bands["lower"].astype(float).rename("lower"),
        ],
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
            previous["upper"],
            previous["lower"],
            current["close"],
            current["upper"],
            current["lower"],
        )

        if any(pd.isna(value) for value in raw_values):
            continue

        previous_close = float(previous["close"])
        previous_upper = float(previous["upper"])
        previous_lower = float(previous["lower"])
        current_close = float(current["close"])
        current_upper = float(current["upper"])
        current_lower = float(current["lower"])

        numeric_values = (
            previous_close,
            previous_upper,
            previous_lower,
            current_close,
            current_upper,
            current_lower,
        )

        if not all(math.isfinite(value) for value in numeric_values):
            continue

        previous_width = previous_upper - previous_lower
        current_width = current_upper - current_lower

        previous_degenerate = (
            previous_width <= 1e-12 or previous_width / max(abs(previous_close), 1e-12) <= 1e-10
        )
        current_degenerate = (
            current_width <= 1e-12 or current_width / max(abs(current_close), 1e-12) <= 1e-10
        )

        if previous_degenerate or current_degenerate:
            continue

        lower_reentry = previous_close <= previous_lower and current_close > current_lower
        upper_reentry = previous_close >= previous_upper and current_close < current_upper

        if lower_reentry:
            events.append(
                IndicatorEvent(
                    indicator="bollinger",
                    position=position,
                    direction="bullish",
                    event="lower_band_reentry",
                    kind="reentry",
                    strength=0.6,
                    metadata={
                        "previous_close": previous_close,
                        "previous_band": previous_lower,
                        "current_close": current_close,
                        "current_band": current_lower,
                    },
                )
            )

        elif upper_reentry:
            events.append(
                IndicatorEvent(
                    indicator="bollinger",
                    position=position,
                    direction="bearish",
                    event="upper_band_reentry",
                    kind="reentry",
                    strength=0.6,
                    metadata={
                        "previous_close": previous_close,
                        "previous_band": previous_upper,
                        "current_close": current_close,
                        "current_band": current_upper,
                    },
                )
            )

    return events


def detect_bollinger_signal(close: pd.Series, bands: dict[str, pd.Series]) -> BollingerPosition:
    """Classe le prix selon sa position normalisée entre les bandes."""
    frame = pd.concat(
        [close.rename("close"), bands["upper"].rename("upper"), bands["lower"].rename("lower")],
        axis=1,
    ).dropna()
    if frame.empty:
        return "neutral"
    row = frame.iloc[-1]
    return _classify_position(float(row["close"]), float(row["upper"]), float(row["lower"]))


def is_bollinger_degenerate(
    close: pd.Series, bands: dict[str, pd.Series], normalized_epsilon: float = 1e-10
) -> bool:
    """Indique qu'une bande ne porte aucune information de position exploitable."""
    frame = pd.concat(
        [close.rename("close"), bands["upper"].rename("upper"), bands["lower"].rename("lower")],
        axis=1,
    ).dropna()
    if frame.empty:
        return False
    row = frame.iloc[-1]
    width = float(row["upper"] - row["lower"])
    return width <= 1e-12 or width / max(abs(float(row["close"])), 1e-12) <= normalized_epsilon


_BOLLINGER_STATE_DIRECTION: dict[str, SignalDirection] = {
    "oversold": "bullish",
    "near_oversold": "bullish",
    "neutral": "neutral",
    "near_overbought": "bearish",
    "overbought": "bearish",
}

#: Force associée à chaque position Bollinger courante (hors événement de
#: cassure/réintégration, prioritaire) selon la convention du package.
_BOLLINGER_STATE_STRENGTH: dict[str, float] = {
    "oversold": 1.0,
    "near_oversold": 0.5,
    "neutral": 0.0,
    "near_overbought": 0.5,
    "overbought": 1.0,
}


def build_bollinger_signal(close: pd.Series, bands: dict[str, pd.Series]) -> IndicatorSignal:
    """Construit le signal structuré des bandes de Bollinger.

    Les événements de transition (``lower_band_breakout``/``lower_band_reentry``
    /``upper_band_breakout``/``upper_band_reentry``), détectés entre les deux
    derniers points valides, sont prioritaires sur l'état courant
    (``state``, identique aux positions de :func:`detect_bollinger_signal`).

    Une cassure de bande basse est baissière (pression vendeuse) et une
    réintégration de bande basse est haussière (rebond potentiel); l'inverse
    s'applique à la bande haute. Un simple contact avec la bande basse n'est
    donc jamais automatiquement traité comme un signal d'achat fort.

    Une bande dégénérée (largeur non exploitable) renvoie un signal neutre de
    statut ``"invalid_data"`` et de force nulle: le statut ``"disabled"`` est
    réservé à un indicateur explicitement désactivé par la configuration
    (ce qui ne peut pas être décidé par ce module purement calculatoire), pas
    à une donnée de marché de qualité insuffisante.
    """
    frame = pd.concat(
        [close.rename("close"), bands["upper"].rename("upper"), bands["lower"].rename("lower")],
        axis=1,
    ).dropna()
    if frame.empty:
        return _unavailable_signal("insufficient_data", "Historique de Bollinger insuffisant")

    current = frame.iloc[-1]
    current_close, current_upper, current_lower = (
        float(current["close"]),
        float(current["upper"]),
        float(current["lower"]),
    )
    if not all(math.isfinite(value) for value in (current_close, current_upper, current_lower)):
        return _unavailable_signal("invalid_data", "Valeurs de Bollinger non finies")
    current_width = current_upper - current_lower
    if current_width <= 1e-12 or current_width / max(abs(current_close), 1e-12) <= 1e-10:
        return IndicatorSignal(
            status="invalid_data",
            direction="neutral",
            signal="neutral",
            state="neutral",
            strength=0.0,
            reason="Bandes de Bollinger dégénérées: largeur non exploitable",
            raw_value=current_close,
        )

    current_position = _classify_position(current_close, current_upper, current_lower)

    event: str | None = None
    if len(frame) >= 2:
        previous = frame.iloc[-2]
        previous_values = (
            float(previous["close"]),
            float(previous["upper"]),
            float(previous["lower"]),
        )
        if not all(math.isfinite(value) for value in previous_values):
            return _unavailable_signal("invalid_data", "Valeurs de Bollinger non finies")
        previous_position = _classify_position(*previous_values)
        was_below, is_below = previous_position == "oversold", current_position == "oversold"
        was_above, is_above = previous_position == "overbought", current_position == "overbought"
        if not was_below and is_below:
            event = "lower_band_breakout"
        elif was_below and not is_below:
            event = "lower_band_reentry"
        elif not was_above and is_above:
            event = "upper_band_breakout"
        elif was_above and not is_above:
            event = "upper_band_reentry"

    components = _bollinger_components(close, bands)
    if event == "lower_band_breakout":
        result = IndicatorSignal(
            status="available",
            direction="bearish",
            signal=event,
            state=current_position,
            strength=_clamp_strength(0.75),
            reason="Cassure sous la bande basse: pression vendeuse",
            raw_value=current_close,
        )
    elif event == "lower_band_reentry":
        result = IndicatorSignal(
            status="available",
            direction="bullish",
            signal=event,
            state=current_position,
            strength=_clamp_strength(0.6),
            reason="Réintégration au-dessus de la bande basse: rebond potentiel",
            raw_value=current_close,
        )
    elif event == "upper_band_breakout":
        result = IndicatorSignal(
            status="available",
            direction="bullish",
            signal=event,
            state=current_position,
            strength=_clamp_strength(0.75),
            reason="Cassure au-dessus de la bande haute: pression acheteuse",
            raw_value=current_close,
        )
    elif event == "upper_band_reentry":
        result = IndicatorSignal(
            status="available",
            direction="bearish",
            signal=event,
            state=current_position,
            strength=_clamp_strength(0.6),
            reason="Réintégration sous la bande haute: essoufflement potentiel",
            raw_value=current_close,
        )
    else:
        result = IndicatorSignal(
            status="available",
            direction=_BOLLINGER_STATE_DIRECTION[current_position],
            signal=current_position,
            state=current_position,
            strength=_clamp_strength(_BOLLINGER_STATE_STRENGTH[current_position]),
            reason=f"Position Bollinger courante: {current_position}",
            raw_value=current_close,
        )
    if components is not None:
        result["components"] = components
    return result
