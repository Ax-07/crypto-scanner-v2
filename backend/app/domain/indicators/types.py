"""Alias de types partagés par les modules d'indicateurs et de confluence."""

from __future__ import annotations

from typing import Literal, Mapping, TypeAlias, TypedDict

MacdSignal: TypeAlias = Literal["bullish", "bearish", "neutral"]
BollingerPosition: TypeAlias = Literal[
    "oversold", "near_oversold", "neutral", "near_overbought", "overbought"
]
StochasticSignal: TypeAlias = Literal[
    "bullish_cross", "oversold", "neutral", "bearish_cross", "overbought"
]
ConfluenceGrade: TypeAlias = Literal["F", "D", "C", "B", "A", "A+"]
TrendState: TypeAlias = Literal["bullish", "bearish", "neutral", "unavailable"]
Availability: TypeAlias = Literal["available", "insufficient_data", "invalid_data", "disabled"]

#: Biais directionnel générique porté par un signal structuré d'indicateur.
SignalDirection: TypeAlias = Literal["bullish", "bearish", "neutral"]

#: Identifiant libre (``str``) de l'événement ou de l'état natif détecté par un
#: indicateur (ex. ``"bullish_cross"``, ``"oversold"``). Volontairement non
#: contraint par un ``Literal`` unique afin que chaque indicateur puisse
#: étendre son propre vocabulaire sans modifier ce module partagé.
SignalEvent: TypeAlias = str

#: Clé d'indicateur reconnue par le module de confluence pour le mode
#: structuré (:data:`IndicatorSignals`).
IndicatorName: TypeAlias = Literal["rsi", "sma", "ema", "macd", "bollinger", "stochastic"]


class IndicatorSignal(TypedDict):
    """Résultat structuré et commun produit par chaque indicateur technique.

    Ce contrat est intentionnellement plat pour rester facile à sérialiser
    (JSON, logs, futurs payloads API) et à étendre lorsque de nouveaux
    indicateurs seront ajoutés. Il complète les fonctions historiques de
    classification (``detect_*_signal``) sans les remplacer.

    Attributes:
        status: Disponibilité du calcul, réutilise :data:`Availability`.
        direction: Biais directionnel (``bullish``/``bearish``/``neutral``).
        signal: Événement ou signal natif principal détecté (ex.
            ``"bullish_cross"``), ou ``None`` si aucune donnée exploitable.
        state: État courant de l'indicateur (ex. ``"oversold"``), ou ``None``
            lorsque l'indicateur ne distingue pas d'état persistant.
        strength: Force du signal, bornée dans ``[0.0, 1.0]``. Ne représente
            pas une probabilité de réussite, voir les docstrings de chaque
            fonction ``detect_*``/``build_*`` pour la convention retenue.
        reason: Explication lisible destinée aux logs ou à l'affichage, ou
            ``None``.
        raw_value: Valeur numérique brute ayant produit le signal (ex. RSI),
            lorsque pertinente et sérialisable, sinon ``None``. Permet un
            calcul de facteur exact dépendant d'un seuil configurable (ex.
            RSI) sans réintroduire de dépendance pandas/numpy dans le
            contrat.
    """

    status: Availability
    direction: SignalDirection
    signal: SignalEvent | None
    state: str | None
    strength: float
    reason: str | None
    raw_value: float | None


#: Ensemble des signaux structurés d'un même snapshot d'indicateurs, indexés
#: par nom (utilisé par ``calculate_confluence_score`` en mode structuré).
IndicatorSignals: TypeAlias = Mapping[IndicatorName, IndicatorSignal]


def _clamp_strength(value: float) -> float:
    """Borne une force de signal dans l'intervalle ``[0.0, 1.0]``."""
    return min(max(float(value), 0.0), 1.0)


def _unavailable_signal(status: Availability, reason: str | None = None) -> IndicatorSignal:
    """Construit un :class:`IndicatorSignal` neutre pour une donnée non exploitable.

    Utilisé par chaque indicateur lorsque l'entrée est absente, insuffisante
    ou invalide (``status`` vaut alors ``"insufficient_data"``,
    ``"invalid_data"`` ou ``"disabled"``).
    """
    return IndicatorSignal(
        status=status,
        direction="neutral",
        signal=None,
        state=None,
        strength=0.0,
        reason=reason,
        raw_value=None,
    )


__all__ = [
    "MacdSignal",
    "BollingerPosition",
    "StochasticSignal",
    "ConfluenceGrade",
    "TrendState",
    "Availability",
    "SignalDirection",
    "SignalEvent",
    "IndicatorName",
    "IndicatorSignal",
    "IndicatorSignals",
]
