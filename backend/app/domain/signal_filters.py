"""Moteur pur et adaptateur legacy des filtres de signaux structurés."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, TypeAlias, cast

from app.domain.indicators.types import IndicatorSignal

FilterField: TypeAlias = Literal["direction", "signal", "state", "status"]
FilterMatch: TypeAlias = Literal["all", "any"]
FilterIndicator: TypeAlias = Literal["macd", "bollinger", "stochastic"]

LEGACY_FILTER_MATRIX: dict[str, dict[str, tuple[FilterField, str]]] = {
    "macd": {
        "bullish": ("direction", "bullish"),
        "bearish": ("direction", "bearish"),
        "neutral": ("direction", "neutral"),
    },
    "bollinger": {
        "oversold": ("state", "oversold"),
        "near_oversold": ("state", "near_oversold"),
        "neutral": ("state", "neutral"),
        "near_overbought": ("state", "near_overbought"),
        "overbought": ("state", "overbought"),
    },
    # La fonction historique donne la priorité aux croisements, puis aux zones.
    # build_stochastic_signal recopie exactement cette classe dans ``signal``.
    # Mapper les zones vers ``state`` accepterait à tort un croisement survenu
    # dans une zone extrême et casserait donc la parité legacy.
    "stochastic": {
        "bullish_cross": ("signal", "bullish_cross"),
        "oversold": ("signal", "oversold"),
        "neutral": ("signal", "neutral"),
        "bearish_cross": ("signal", "bearish_cross"),
        "overbought": ("signal", "overbought"),
    },
}


def include_disabled_filter_signals(
    *,
    indicator_signals: Mapping[str, IndicatorSignal],
    disabled_indicators: Sequence[str],
) -> dict[str, IndicatorSignal]:
    """Crée une vue locale où les désactivations sont filtrables explicitement."""
    completed = dict(indicator_signals)
    for indicator in disabled_indicators:
        completed.setdefault(
            indicator,
            IndicatorSignal(
                status="disabled",
                direction="neutral",
                signal=None,
                state=None,
                strength=0.0,
                reason="Indicateur désactivé par la configuration",
                raw_value=None,
            ),
        )
    return completed


def _condition(field: FilterField, values: Sequence[str]) -> dict[str, object]:
    return {"field": field, "values": list(values)}


def _legacy_indicator_filter(
    indicator: FilterIndicator,
    values: Sequence[str] | None,
) -> dict[str, object] | None:
    """Convertit une liste legacy en conditions sans modifier sa logique OR."""
    if not values:
        return None
    grouped: dict[FilterField, list[str]] = {}
    for value in values:
        mapping = LEGACY_FILTER_MATRIX[indicator].get(value)
        if mapping is None:
            raise ValueError(f"valeur legacy inconnue pour {indicator}: {value}")
        field, structured_value = mapping
        grouped.setdefault(field, []).append(structured_value)
    return {
        "match": "any",
        "conditions": [_condition(field, items) for field, items in grouped.items()],
    }


def legacy_filters_to_structured(
    *,
    filter_macd: Sequence[str] | None,
    filter_bb: Sequence[str] | None,
    filter_stoch: Sequence[str] | None,
) -> dict[str, object] | None:
    """Convertit les trois filtres historiques vers le contrat structuré v1."""
    indicators: dict[str, object] = {}
    for name, values in (
        ("macd", filter_macd),
        ("bollinger", filter_bb),
        ("stochastic", filter_stoch),
    ):
        converted = _legacy_indicator_filter(cast(FilterIndicator, name), values)
        if converted is not None:
            indicators[name] = converted
    if not indicators:
        return None
    return {"version": 1, "indicators": indicators}


def resolve_effective_signal_filters(
    *,
    structured_filters: Mapping[str, object] | None,
    filter_macd: Sequence[str] | None,
    filter_bb: Sequence[str] | None,
    filter_stoch: Sequence[str] | None,
) -> dict[str, object] | None:
    """Applique la priorité structurée et le fallback legacy par indicateur."""
    legacy = legacy_filters_to_structured(
        filter_macd=filter_macd,
        filter_bb=filter_bb,
        filter_stoch=filter_stoch,
    )
    if structured_filters is None:
        return legacy
    version = structured_filters.get("version")
    if version != 1:
        raise ValueError(f"version de filtres structurés non prise en charge: {version}")
    raw_indicators = structured_filters.get("indicators", {})
    if not isinstance(raw_indicators, Mapping):
        raise ValueError("indicators doit être un mapping")
    indicators = dict(raw_indicators)
    if legacy is not None:
        legacy_indicators = cast(Mapping[str, object], legacy["indicators"])
        for name, group in legacy_indicators.items():
            indicators.setdefault(name, group)
    return {"version": 1, "indicators": indicators}


def _condition_matches(signal: IndicatorSignal, condition: Mapping[str, object]) -> bool:
    field = condition.get("field")
    if field not in {"direction", "signal", "state", "status"}:
        raise ValueError(f"champ de filtre structuré inconnu: {field}")
    values = condition.get("values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        raise ValueError("values doit être une liste non vide")
    return signal[field] in values


def check_structured_signal_filters(
    *,
    indicator_signals: Mapping[str, IndicatorSignal],
    filters: Mapping[str, object],
) -> bool:
    """Évalue le contrat v1 sans mutation ni dépendance à FastAPI ou CCXT.

    Les valeurs d'une condition sont combinées en OR. Les conditions suivent
    ``match`` (``all``/``any``) et les indicateurs sont toujours combinés en
    AND. Sans condition de statut explicite, un groupe non vide exige un signal
    ``available`` afin de ne pas confondre neutralité et indisponibilité.
    """
    version = filters.get("version")
    if version != 1:
        raise ValueError(f"version de filtres structurés non prise en charge: {version}")
    indicators = filters.get("indicators", {})
    if not isinstance(indicators, Mapping):
        raise ValueError("indicators doit être un mapping")

    for indicator, raw_group in indicators.items():
        if indicator not in LEGACY_FILTER_MATRIX:
            raise ValueError(f"indicateur de filtre structuré inconnu: {indicator}")
        if not isinstance(raw_group, Mapping):
            raise ValueError(f"filtre invalide pour {indicator}")
        match = raw_group.get("match", "all")
        if match not in {"all", "any"}:
            raise ValueError(f"stratégie de correspondance inconnue: {match}")
        conditions = raw_group.get("conditions", [])
        if not isinstance(conditions, Sequence) or isinstance(conditions, (str, bytes)):
            raise ValueError("conditions doit être une liste")
        if not conditions:
            continue
        signal = indicator_signals.get(indicator)
        if signal is None:
            return False
        typed_conditions: list[Mapping[str, object]] = []
        for condition in conditions:
            if not isinstance(condition, Mapping):
                raise ValueError("une condition doit être un mapping")
            typed_conditions.append(condition)
        has_status = any(condition.get("field") == "status" for condition in typed_conditions)
        if not has_status and signal["status"] != "available":
            return False
        matches = [_condition_matches(signal, condition) for condition in typed_conditions]
        if (match == "all" and not all(matches)) or (match == "any" and not any(matches)):
            return False
    return True


__all__ = [
    "FilterField",
    "FilterIndicator",
    "FilterMatch",
    "LEGACY_FILTER_MATRIX",
    "check_structured_signal_filters",
    "include_disabled_filter_signals",
    "legacy_filters_to_structured",
    "resolve_effective_signal_filters",
]
