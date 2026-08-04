"""Construction causale des lignes du dataset de machine learning."""

from __future__ import annotations

import math
from collections import Counter
from typing import Final, Literal

from app.models.backtest import ForwardOutcome, SignalObservation
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MLFeatureValue,
    MarketDirectionLabel,
)

ML_TARGET_HORIZON: Final[Literal[6]] = 6


class MLDatasetBuildError(ValueError):
    """Erreur explicite empêchant la construction d'une ligne ML fiable."""


def _feature_token(value: str) -> str:
    """Normalise une valeur catégorielle utilisée dans un nom de feature."""
    normalized = "".join(
        character.lower() if character.isalnum() else "_" for character in value.strip()
    )
    token = "_".join(part for part in normalized.split("_") if part)
    return token or "unknown"


def _add_scalar_feature(
    features: dict[str, MLFeatureValue],
    name: str,
    value: object,
) -> None:
    """Ajoute uniquement une valeur scalaire compatible et finie."""
    if value is None:
        return

    if isinstance(value, bool):
        features[name] = value
        return

    if isinstance(value, int):
        features[name] = value
        return

    if isinstance(value, float):
        if math.isfinite(value):
            features[name] = value
        return

    if isinstance(value, str):
        features[name] = value


def extract_causal_features(
    observation: SignalObservation,
) -> dict[str, MLFeatureValue]:
    """Aplatit les informations connues à la bougie de décision.

    Les données futures, les prix de sortie, MFE/MAE et métadonnées
    d'outcome ne sont jamais reçus par cette fonction.
    """
    features: dict[str, MLFeatureValue] = {}

    _add_scalar_feature(
        features,
        "price.close",
        observation.close,
    )
    _add_scalar_feature(
        features,
        "observation.accepted",
        observation.accepted,
    )
    _add_scalar_feature(
        features,
        "trend.score",
        observation.trend_score,
    )
    _add_scalar_feature(
        features,
        "trend.net_score",
        observation.trend_net_score,
    )
    _add_scalar_feature(
        features,
        "confluence.score",
        observation.confluence_score,
    )
    _add_scalar_feature(
        features,
        "confluence.grade",
        observation.confluence_grade,
    )

    for field_name, value in sorted(observation.source_ohlcv.items()):
        _add_scalar_feature(
            features,
            f"candle.{_feature_token(field_name)}",
            value,
        )

    for timeframe, state in sorted(observation.trend_states.items()):
        _add_scalar_feature(
            features,
            f"trend.state.{_feature_token(timeframe)}",
            state,
        )

    for indicator, availability in sorted(observation.availability.items()):
        _add_scalar_feature(
            features,
            f"availability.{_feature_token(indicator)}",
            availability,
        )

    for factor_name, factor_value in sorted(observation.confluence_factors.items()):
        _add_scalar_feature(
            features,
            f"confluence.factor.{_feature_token(factor_name)}",
            factor_value,
        )

    for indicator_name, signal in sorted(observation.indicator_signals.items()):
        indicator = _feature_token(indicator_name)
        prefix = f"indicator.{indicator}"

        _add_scalar_feature(
            features,
            f"{prefix}.status",
            signal.status,
        )
        _add_scalar_feature(
            features,
            f"{prefix}.direction",
            signal.direction,
        )
        _add_scalar_feature(
            features,
            f"{prefix}.signal",
            signal.signal,
        )
        _add_scalar_feature(
            features,
            f"{prefix}.state",
            signal.state,
        )
        _add_scalar_feature(
            features,
            f"{prefix}.strength",
            signal.strength,
        )
        _add_scalar_feature(
            features,
            f"{prefix}.raw_value",
            signal.raw_value,
        )

        for component_name, component in sorted((signal.components or {}).items()):
            component_token = _feature_token(component_name)
            component_prefix = f"{prefix}.component.{component_token}"

            _add_scalar_feature(
                features,
                f"{component_prefix}.value",
                component.value,
            )
            _add_scalar_feature(
                features,
                f"{component_prefix}.normalized_value",
                component.normalized_value,
            )
            _add_scalar_feature(
                features,
                f"{component_prefix}.unit",
                component.unit,
            )

    event_counts: Counter[str] = Counter()
    event_max_strengths: dict[str, float] = {}

    for event in observation.indicator_events:
        indicator = _feature_token(str(event.indicator))
        event_name = _feature_token(event.event)
        event_kind = _feature_token(str(event.kind))
        direction = _feature_token(str(event.direction))

        event_counts["event.total_count"] += 1
        event_counts[f"event.direction.{direction}.count"] += 1
        event_counts[f"event.indicator.{indicator}.count"] += 1
        event_counts[f"event.kind.{event_kind}.count"] += 1
        event_counts[f"event.{indicator}.{event_name}.count"] += 1

        event_strength = event.strength

        if event_strength is not None:
            strength_key = f"event.{indicator}.{event_name}.max_strength"
            previous_strength = event_max_strengths.get(
                strength_key,
                0.0,
            )
            event_max_strengths[strength_key] = max(
                previous_strength,
                event_strength,
            )

    for name, count in sorted(event_counts.items()):
        features[name] = count

    for name, strength in sorted(event_max_strengths.items()):
        features[name] = strength

    divergence_counts: Counter[str] = Counter()

    for divergence in observation.divergences:
        divergence_counts["divergence.total_count"] += 1

        source = divergence.get("source")
        divergence_type = divergence.get("divergence_type")

        if isinstance(source, str):
            source_token = _feature_token(source)
            divergence_counts[f"divergence.source.{source_token}.count"] += 1

        if isinstance(divergence_type, str):
            type_token = _feature_token(divergence_type)
            divergence_counts[f"divergence.type.{type_token}.count"] += 1

            if isinstance(source, str):
                source_token = _feature_token(source)
                divergence_counts[f"divergence.{source_token}.{type_token}.count"] += 1

    for name, count in sorted(divergence_counts.items()):
        features[name] = count

    for quality_name, value in sorted(observation.quality.items()):
        _add_scalar_feature(
            features,
            f"quality.{_feature_token(quality_name)}",
            value,
        )

    return features


def extract_natr_percent(
    observation: SignalObservation,
) -> float:
    """Extrait le NATR causal utilisé pour définir la zone neutre."""
    atr_signal = observation.indicator_signals.get("atr")

    if atr_signal is None or atr_signal.status != "available":
        raise MLDatasetBuildError("NATR indisponible : le signal ATR doit être disponible")

    natr_component = (atr_signal.components or {}).get("natr")

    natr_percent: float | None = None

    if natr_component is not None:
        if natr_component.value is not None:
            natr_percent = float(natr_component.value)
        elif natr_component.normalized_value is not None:
            natr_percent = float(natr_component.normalized_value) * 100

    if natr_percent is None and atr_signal.raw_value is not None:
        natr_percent = float(atr_signal.raw_value)

    if natr_percent is None or not math.isfinite(natr_percent) or natr_percent <= 0:
        raise MLDatasetBuildError("NATR indisponible, non fini ou inférieur ou égal à zéro")

    return natr_percent


def classify_market_direction(
    future_return: float,
    neutral_threshold_return: float,
) -> MarketDirectionLabel:
    """Classe le rendement futur avec des bornes neutres inclusives."""
    if not math.isfinite(future_return):
        raise MLDatasetBuildError("le rendement futur doit être fini")

    if not math.isfinite(neutral_threshold_return) or neutral_threshold_return <= 0:
        raise MLDatasetBuildError("le seuil neutre doit être fini et strictement positif")

    if future_return > neutral_threshold_return:
        return MarketDirectionLabel.UP

    if future_return < -neutral_threshold_return:
        return MarketDirectionLabel.DOWN

    return MarketDirectionLabel.NEUTRAL


def build_ml_dataset_row(
    observation: SignalObservation,
    outcome: ForwardOutcome,
    *,
    natr_multiplier: float = 1.0,
) -> MLDatasetRow:
    """Associe une observation causale à son outcome à six bougies."""
    if observation.id is None:
        raise MLDatasetBuildError("l'observation doit être persistée et posséder un identifiant")

    if observation.snapshot_status != "confirmed":
        raise MLDatasetBuildError("seules les observations confirmées sont acceptées")

    if outcome.observation_id is not None:
        if outcome.observation_id != observation.id:
            raise MLDatasetBuildError("l'outcome n'appartient pas à l'observation fournie")

    if outcome.horizon != ML_TARGET_HORIZON:
        raise MLDatasetBuildError(f"l'horizon doit être égal à {ML_TARGET_HORIZON}")

    if outcome.censored:
        raise MLDatasetBuildError("un outcome censuré ne peut pas produire de ligne ML")

    if not outcome.valid:
        raise MLDatasetBuildError("un outcome invalide ne peut pas produire de ligne ML")

    if outcome.gross_return is None:
        raise MLDatasetBuildError("gross_return est requis pour construire le label")

    if outcome.entry_time is None or outcome.exit_time is None:
        raise MLDatasetBuildError("entry_time et exit_time sont requis")

    if not math.isfinite(natr_multiplier) or natr_multiplier <= 0 or natr_multiplier > 10:
        raise MLDatasetBuildError(
            "natr_multiplier doit être fini, supérieur à zéro " "et inférieur ou égal à 10"
        )

    natr_percent = extract_natr_percent(observation)
    neutral_threshold_return = natr_percent / 100 * natr_multiplier
    future_return = float(outcome.gross_return)
    label = classify_market_direction(
        future_return,
        neutral_threshold_return,
    )

    features = extract_causal_features(observation)
    features["volatility.natr_percent"] = natr_percent

    return MLDatasetRow(
        observation_id=observation.id,
        job_id=observation.job_id,
        symbol=observation.symbol,
        timeframe=observation.timeframe,
        decision_time=observation.decision_time,
        source_open_time=observation.source_open_time,
        snapshot_status="confirmed",
        calculation_mode="canonical",
        source_algorithm_version=observation.algorithm_version,
        source_dataset_version=observation.dataset_version,
        profile_id=observation.profile_id,
        profile_fingerprint=observation.profile_fingerprint,
        horizon=ML_TARGET_HORIZON,
        entry_policy=outcome.entry_policy,
        entry_time=outcome.entry_time,
        exit_time=outcome.exit_time,
        natr_percent=natr_percent,
        natr_multiplier=natr_multiplier,
        neutral_threshold_return=neutral_threshold_return,
        future_return=future_return,
        label=label,
        features=features,
    )
