"""Filtrage de signaux et calcul du score de confluence pondéré."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.indicators.types import Availability, IndicatorSignal, TrendState

__all__ = [
    "check_signal_filters",
    "calculate_confluence_score",
    "calculate_signal_factor",
    "calculate_rsi_signal_factor",
    "calculate_trend_signal_factor",
]

#: Mappe l'état RSI structuré (:func:`app.domain.indicators.rsi.detect_rsi_signal`)
#: vers un facteur de confluence. Contrairement au mode historique (continu,
#: basé sur ``rsi_value``/``rsi_threshold``), cette table est discrète: elle
#: approxime les mêmes seuils (``oversold`` ≈ ``rsi <= 30``, ``near_oversold``
#: ≈ zone de seuil, le reste ≈ ``rsi >= 50``).
_RSI_STATE_FACTOR: dict[str, float] = {
    "oversold": 1.0,
    "near_oversold": 0.75,
    "neutral": 0.3,
    "near_overbought": 0.0,
    "overbought": 0.0,
}

#: Mappe l'événement/état structuré d'une moyenne mobile (SMA ou EMA, même
#: vocabulaire pour les deux familles) vers un facteur de tendance individuel,
#: agrégé ensuite par :func:`calculate_trend_signal_factor`.
_MOVING_AVERAGE_FACTOR: dict[str, float] = {
    "bullish_cross": 1.0,
    "bullish_alignment": 1.0,
    "price_above": 0.75,
    "neutral": 0.5,
    "price_below": 0.25,
    "bearish_alignment": 0.0,
    "bearish_cross": 0.0,
}

#: Mappe la direction structurée du MACD vers le facteur historique
#: (``bullish``/``neutral``/``bearish``), les croisements partageant déjà la
#: direction correspondante.
_MACD_DIRECTION_FACTOR: dict[str, float] = {"bullish": 1.0, "neutral": 0.4, "bearish": 0.0}

#: Identique à la table historique de :func:`calculate_confluence_score`;
#: appliquée sur ``state`` (position Bollinger), inchangée par un éventuel
#: événement de cassure/réintégration.
_BOLLINGER_STATE_FACTOR: dict[str, float] = {
    "oversold": 1.0,
    "near_oversold": 0.75,
    "neutral": 0.35,
    "near_overbought": 0.1,
    "overbought": 0.0,
}

#: Identique à la table historique de :func:`calculate_confluence_score`;
#: appliquée sur ``signal`` (événement de croisement ou zone extrême, même
#: vocabulaire que l'ancien paramètre ``stoch_signal``).
_STOCHASTIC_SIGNAL_FACTOR: dict[str, float] = {
    "bullish_cross": 1.0,
    "oversold": 0.9,
    "neutral": 0.35,
    "bearish_cross": 0.1,
    "overbought": 0.0,
}


def calculate_signal_factor(indicator: str, signal: IndicatorSignal) -> float | None:
    """Convertit un :class:`IndicatorSignal` structuré en facteur de confluence ``[0, 1]``.

    Retourne ``None`` si le signal n'est pas disponible (``status`` différent
    de ``"available"``) ou si son événement/état n'est pas reconnu pour cet
    indicateur; l'appelant doit alors traiter l'indicateur comme non
    participant, exactement comme en mode historique. Le facteur n'est
    jamais dérivé de ``strength`` seul: chaque indicateur a sa propre table
    de correspondance, documentée avec les constantes du module.

    ``indicator`` attend l'une des clés de :data:`app.domain.indicators.types.IndicatorName`
    (``"rsi"``, ``"sma"``, ``"ema"``, ``"macd"``, ``"bollinger"``, ``"stochastic"``).
    """
    if signal["status"] != "available":
        return None
    if indicator == "rsi":
        return _RSI_STATE_FACTOR.get(signal["state"] or "")
    if indicator in ("sma", "ema"):
        return _MOVING_AVERAGE_FACTOR.get(signal["signal"] or "")
    if indicator == "macd":
        return _MACD_DIRECTION_FACTOR.get(signal["direction"])
    if indicator == "bollinger":
        return _BOLLINGER_STATE_FACTOR.get(signal["state"] or "")
    if indicator == "stochastic":
        return _STOCHASTIC_SIGNAL_FACTOR.get(signal["signal"] or "")
    return None


def calculate_rsi_signal_factor(
    signal: IndicatorSignal,
    *,
    rsi_threshold: float,
) -> float | None:
    """Reproduit exactement le facteur RSI historique à partir d'un signal structuré.

    Le seul champ ``state`` de :func:`app.domain.indicators.rsi.detect_rsi_signal`
    ne permet pas de distinguer toutes les branches historiques dépendant de
    ``rsi_threshold`` (un seuil configurable): par exemple ``rsi=45`` et
    ``rsi=55`` produisent tous deux ``state="neutral"`` pour les niveaux par
    défaut, alors que leurs facteurs historiques diffèrent (0,30 vs 0,00).
    Cette fonction utilise donc ``signal["raw_value"]`` (la valeur RSI brute)
    plutôt que ``state``/``signal``, en appliquant exactement les règles
    historiques de :func:`calculate_confluence_score`.

    Retourne ``None`` si le signal est indisponible ou si ``raw_value`` est
    absent/non fini (aucune valeur RSI exploitable).
    """
    if signal["status"] != "available":
        return None
    raw_value = signal.get("raw_value")
    if raw_value is None or not math.isfinite(raw_value):
        return None
    if raw_value <= 30:
        return 1.0
    if raw_value <= rsi_threshold:
        return 0.75
    if raw_value < 50:
        return 0.3
    return 0.0


def calculate_trend_signal_factor(signals: Sequence[IndicatorSignal]) -> float | None:
    """Agrège des signaux structurés de moyennes mobiles (SMA et/ou EMA) en un
    facteur de tendance unique, comparable au mode historique
    (``bullish`` ≈ 1.0, ``neutral`` ≈ 0.5, ``bearish`` ≈ 0.0).

    Les signaux non disponibles ou à l'état non reconnu sont ignorés. Un
    désaccord entre familles se traduit naturellement par une moyenne proche
    de ``0.5``, comme le fait déjà ``detect_trend`` avec ``"neutral"``.
    Retourne ``None`` si aucun signal exploitable n'est fourni.
    """
    factors = [
        factor
        for signal in signals
        if (factor := calculate_signal_factor("sma", signal)) is not None
    ]
    if not factors:
        return None
    return sum(factors) / len(factors)


def check_signal_filters(
    *,
    macd_signal: str | None,
    bb_position: str | None,
    stoch_signal: str | None,
    filter_macd: Sequence[str] | None,
    filter_bb: Sequence[str] | None,
    filter_stoch: Sequence[str] | None,
) -> bool:
    """Vérifie que chaque signal actif appartient à son filtre autorisé."""
    checks = (
        (filter_macd, macd_signal),
        (filter_bb, bb_position),
        (filter_stoch, stoch_signal),
    )
    return all(not allowed or value in allowed for allowed, value in checks)


def calculate_confluence_score(
    *,
    rsi_value: float | None,
    rsi_threshold: float,
    trend_score: int | None,
    max_trend_score: int,
    macd_signal: str | None,
    bb_position: str | None,
    stoch_signal: str | None,
    weights: dict[str, float],
    trend_states: Sequence[TrendState] | None = None,
    availability: dict[str, Availability] | None = None,
    raw_values: dict[str, Any] | None = None,
    indicator_signals: Mapping[str, IndicatorSignal] | None = None,
) -> dict[str, Any] | None:
    """Calcule un score de confluence pondéré et renormalisé sur 100.

    Seuls les facteurs disponibles avec un poids strictement positif participent.
    Le résultat contient le score, le grade, les contributions ``breakdown`` et
    les poids effectifs. ``None`` indique qu'aucun poids exploitable ne subsiste.

    ``indicator_signals`` active un mode structuré optionnel et rétrocompatible:
    pour chaque clé présente (``"rsi"``, ``"macd"``, ``"bollinger"``,
    ``"stochastic"``, et ``"sma"``/``"ema"`` agrégées en ``"trend"``), le
    :class:`IndicatorSignal` fourni est prioritaire sur l'argument historique
    correspondant, y compris lorsqu'il ne produit aucun facteur exploitable
    (l'indicateur ne participe alors pas, même si l'argument historique
    aurait donné un résultat). Le fallback historique ne s'applique qu'en
    l'absence totale de la clé structurée correspondante. Les indicateurs
    sans clé structurée continuent d'utiliser exclusivement les arguments
    historiques.
    """
    factors: dict[str, float] = {}

    if rsi_value is not None and math.isfinite(rsi_value) and rsi_value <= 30:
        factors["rsi"] = 1.0
    elif rsi_value is not None and math.isfinite(rsi_value) and rsi_value <= rsi_threshold:
        factors["rsi"] = 0.75
    elif rsi_value is not None and math.isfinite(rsi_value) and rsi_value < 50:
        factors["rsi"] = 0.3
    elif rsi_value is not None and math.isfinite(rsi_value):
        factors["rsi"] = 0.0

    if trend_states is not None:
        available_trends = [state for state in trend_states if state != "unavailable"]
        if available_trends:
            trend_factors = {"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}
            factors["trend"] = sum(trend_factors[state] for state in available_trends) / len(
                available_trends
            )
    elif trend_score is not None and math.isfinite(trend_score) and max_trend_score > 0:
        factors["trend"] = min(max(trend_score / max_trend_score, 0), 1)
    if macd_signal is not None:
        factors["macd"] = {"bullish": 1.0, "neutral": 0.4, "bearish": 0.0}.get(macd_signal, 0.0)
    bollinger_factor = {
        "oversold": 1.0,
        "near_oversold": 0.75,
        "neutral": 0.35,
        "near_overbought": 0.1,
        "overbought": 0.0,
    }.get(bb_position or "")
    if bollinger_factor is not None:
        factors["bollinger"] = bollinger_factor
    stochastic_factor = {
        "bullish_cross": 1.0,
        "oversold": 0.9,
        "neutral": 0.35,
        "bearish_cross": 0.1,
        "overbought": 0.0,
    }.get(stoch_signal or "")
    if stochastic_factor is not None:
        factors["stochastic"] = stochastic_factor

    structured_meta: dict[str, IndicatorSignal] = {}
    signals = indicator_signals or {}
    for indicator in ("rsi", "macd", "bollinger", "stochastic"):
        signal = signals.get(indicator)
        if signal is None:
            continue
        structured_meta[indicator] = signal
        factor = (
            calculate_rsi_signal_factor(signal, rsi_threshold=rsi_threshold)
            if indicator == "rsi"
            else calculate_signal_factor(indicator, signal)
        )
        if factor is None:
            factors.pop(indicator, None)
        else:
            factors[indicator] = factor
    trend_inputs = [signals[key] for key in ("sma", "ema") if key in signals]
    if trend_inputs:
        for key in ("sma", "ema"):
            if key in signals:
                structured_meta[key] = signals[key]
        trend_factor = calculate_trend_signal_factor(trend_inputs)
        if trend_factor is None:
            factors.pop("trend", None)
        else:
            factors["trend"] = trend_factor

    active_weights = {
        name: weight for name, weight in weights.items() if name in factors and weight > 0
    }
    total_weight = sum(active_weights.values())
    if total_weight <= 0:
        return None
    effective_weights = {
        name: round(weight / total_weight * 100, 2) for name, weight in active_weights.items()
    }
    breakdown = {
        name: round(factors[name] * weight / total_weight * 100, 2)
        for name, weight in active_weights.items()
    }
    score = round(
        sum(factors[name] * weight for name, weight in active_weights.items()) / total_weight * 100,
        2,
    )
    grade = (
        "A+"
        if score >= 90
        else (
            "A"
            if score >= 80
            else "B" if score >= 70 else "C" if score >= 60 else "D" if score >= 50 else "F"
        )
    )
    statuses = availability or {}
    values = raw_values or {}

    def _structured_source(name: str) -> IndicatorSignal | None:
        if name == "trend":
            return structured_meta.get("sma") or structured_meta.get("ema")
        return structured_meta.get(name)

    details: dict[str, dict[str, Any]] = {}
    for name, configured_weight in weights.items():
        structured_source = _structured_source(name)
        details[name] = {
            "status": (
                structured_source["status"]
                if structured_source is not None
                else statuses.get(name, "available" if name in factors else "insufficient_data")
            ),
            "raw_value": (
                structured_source.get("raw_value")
                if structured_source is not None
                else values.get(name)
            ),
            "signal": values.get(f"{name}_signal"),
            "factor": factors.get(name),
            "configured_weight": configured_weight,
            "effective_weight": effective_weights.get(name),
            "contribution": breakdown.get(name),
            "reason": (
                structured_source["reason"]
                if structured_source is not None
                else (
                    None
                    if statuses.get(name, "available" if name in factors else "insufficient_data")
                    == "available"
                    else statuses.get(name, "insufficient_data")
                )
            ),
            "structured_signal": (
                structured_source["signal"] if structured_source is not None else None
            ),
            "structured_state": (
                structured_source["state"] if structured_source is not None else None
            ),
            "direction": (
                structured_source["direction"] if structured_source is not None else None
            ),
            "strength": (structured_source["strength"] if structured_source is not None else None),
        }
    return {
        "score": score,
        "grade": grade,
        "breakdown": breakdown,
        "effective_weights": effective_weights,
        "details": details,
    }
