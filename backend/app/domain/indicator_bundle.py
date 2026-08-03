"""Builder commun pour construire les signaux structurés (``IndicatorSignal``).

Ce module factorise, en un seul endroit, la construction des ``IndicatorSignal``
consommés par :func:`app.domain.indicators.confluence.calculate_confluence_score`
en mode structuré. Il est utilisé par le moteur canonique
(:mod:`app.domain.backtesting`, partagé par le scanner et le backtest) et par
:mod:`app.services.market_stream`, afin d'éviter toute duplication de la
logique de construction entre ces services.

Décisions de conception:

- Le statut ``"disabled"`` n'est renvoyé que lorsque le flag ``use_*``
  correspondant est ``False`` — jamais pour un historique insuffisant ou une
  donnée invalide, ce qui reste du ressort des fonctions ``detect_*_signal``/
  ``build_*_signal`` de chaque indicateur.
- Les clés ``sma``/``ema`` ne sont ajoutées que si les séries rapides
  correspondantes sont fournies: le scanner et le backtest, qui gèrent une
  tendance multi-timeframes distincte via ``trend_states``/``trend_score``,
  n'utilisent délibérément pas ce builder pour la tendance et n'appellent
  cette fonction qu'avec ``use_sma=False``/``use_ema=False`` (valeurs par
  défaut). Seul :mod:`app.services.market_stream` (tendance sur un seul
  timeframe) fournit ces séries.
- Stochastique: lorsque l'historique disponible ne compte qu'une seule ligne
  valide (``%K``/``%D`` définis simultanément une seule fois), la fonction
  historique :func:`app.domain.indicators.stochastic.detect_stochastic_signal`
  renvoie inconditionnellement ``"neutral"`` (elle exige au moins deux points
  pour toute autre classification), alors que
  :func:`app.domain.indicators.stochastic.build_stochastic_signal` classerait
  cette ligne unique selon la zone réelle de ``%K``/``%D``. Pour préserver une
  parité stricte avec le mode historique dans ce cas limite, ce builder force
  alors un statut ``"insufficient_data"`` (l'indicateur ne participe pas au
  score structuré ce tour-ci, comme un historique vraiment insuffisant). En
  pratique, ce cas ne se produit qu'à l'amorçage et disparaît dès que
  ``min_ohlcv_bars`` (toujours trop grand pour laisser un tel cas isolé
  subsister) est respecté.
"""

from __future__ import annotations

import pandas as pd

from app.domain.indicators.adx import build_adx_signal, calculate_adx_dmi, detect_adx_events
from app.domain.indicators.atr import (
    build_atr_signal,
    calculate_atr,
    calculate_natr,
    detect_atr_events,
)
from app.domain.indicators.bollinger import build_bollinger_signal, detect_bollinger_events
from app.domain.indicators.donchian import (
    build_donchian_signal,
    calculate_donchian_channels,
    detect_donchian_events,
)
from app.domain.indicators.keltner import (
    build_keltner_signal,
    calculate_keltner_channels,
    detect_keltner_events,
)
from app.domain.indicators.macd import build_macd_signal, detect_macd_events
from app.domain.indicators.moving_averages import (
    calculate_ema,
    detect_moving_average_events,
    detect_moving_average_signal,
)
from app.domain.indicators.rsi import detect_rsi_signal, detect_rsi_events
from app.domain.indicators.stochastic import build_stochastic_signal, detect_stochastic_events
from app.domain.indicators.supertrend import (
    build_supertrend_signal,
    calculate_supertrend,
    detect_supertrend_events,
)
from app.domain.indicators.types import IndicatorSignal, _unavailable_signal, IndicatorEvent
from app.domain.indicators.wilder import calculate_true_range

__all__ = [
    "build_indicator_events",
    "build_indicator_signals",
    "calculate_extended_indicator_bundle",
]


def calculate_extended_indicator_bundle(
    *,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    use_atr: bool = False,
    atr_period: int = 14,
    use_adx: bool = False,
    adx_period: int = 14,
    adx_weak_threshold: float = 20,
    adx_strong_threshold: float = 25,
    use_supertrend: bool = False,
    supertrend_atr_period: int = 10,
    supertrend_multiplier: float = 3.0,
    use_donchian: bool = False,
    donchian_period: int = 20,
    use_keltner: bool = False,
    keltner_ema_period: int = 20,
    keltner_atr_period: int = 10,
    keltner_multiplier: float = 2.0,
) -> tuple[dict[str, dict[str, pd.Series]], dict[str, IndicatorSignal]]:
    """Calcule une seule fois les primitives communes et construit les signaux.

    Le True Range est mutualisé. L'ATR public et l'ATR interne de Supertrend
    partagent aussi leur série lorsque leurs périodes sont identiques.
    """
    if not any((use_atr, use_adx, use_supertrend, use_donchian, use_keltner)):
        return {}, {}
    true_range = calculate_true_range(high, low, close)
    data: dict[str, dict[str, pd.Series]] = {}
    atr_by_period: dict[int, dict[str, pd.Series]] = {}

    def atr_for(period: int) -> dict[str, pd.Series]:
        if period not in atr_by_period:
            atr_by_period[period] = calculate_atr(
                high,
                low,
                close,
                period,
                true_range=true_range,
            )
            atr_by_period[period]["natr"] = calculate_natr(
                atr_by_period[period]["atr"],
                close,
            )
        return atr_by_period[period]

    signals: dict[str, IndicatorSignal] = {}
    if use_atr:
        data["atr"] = atr_for(atr_period)
        signals["atr"] = build_atr_signal(data["atr"], close)
    if use_adx:
        data["adx"] = calculate_adx_dmi(
            high,
            low,
            close,
            adx_period,
            true_range=true_range,
        )
        signals["adx"] = build_adx_signal(
            data["adx"],
            weak_threshold=adx_weak_threshold,
            strong_threshold=adx_strong_threshold,
        )
    if use_supertrend:
        supertrend_atr = atr_for(supertrend_atr_period)["atr"]
        data["supertrend"] = calculate_supertrend(
            high,
            low,
            close,
            supertrend_atr_period,
            supertrend_multiplier,
            atr=supertrend_atr,
        )
        signals["supertrend"] = build_supertrend_signal(data["supertrend"], close)
    if use_donchian:
        data["donchian"] = calculate_donchian_channels(
            high,
            low,
            close,
            donchian_period,
        )
        signals["donchian"] = build_donchian_signal(data["donchian"], close)
    if use_keltner:
        keltner_atr = atr_for(keltner_atr_period)["atr"]
        data["keltner"] = calculate_keltner_channels(
            high,
            low,
            close,
            keltner_ema_period,
            keltner_atr_period,
            keltner_multiplier,
            atr=keltner_atr,
            middle_line=calculate_ema(close, keltner_ema_period),
        )
        signals["keltner"] = build_keltner_signal(data["keltner"], close)
    return data, signals


def build_indicator_events(
    *,
    close_series: pd.Series | None = None,
    rsi_series: pd.Series | None = None,
    rsi_oversold_level: float = 30,
    rsi_overbought_level: float = 70,
    ema_fast: pd.Series | None = None,
    ema_slow: pd.Series | None = None,
    macd_data: dict[str, pd.Series] | None = None,
    bollinger_bands: dict[str, pd.Series] | None = None,
    stochastic_data: dict[str, pd.Series] | None = None,
    stochastic_oversold_level: float = 20,
    stochastic_overbought_level: float = 80,
    adx_weak_threshold: float = 20,
    extended_data: dict[str, dict[str, pd.Series]] | None = None,
    only_last: bool = False,
) -> list[IndicatorEvent]:
    """Agrège les événements ponctuels des indicateurs.

    Aucun indicateur n'est recalculé ici. La fonction exploite uniquement
    les séries déjà produites par les calculateurs d'indicateurs.

    Args:
        rsi_series: Série RSI déjà calculée.
        rsi_oversold_level: Seuil RSI de survente.
        rsi_overbought_level: Seuil RSI de surachat.
        ema_fast: Série EMA rapide déjà calculée.
        ema_slow: Série EMA lente déjà calculée.
        macd_data: Séries MACD, signal et histogramme déjà calculées.
        extended_data: Données des indicateurs étendus déjà calculées.
        only_last: Lorsque vrai, ne recherche que les événements présents
            sur la dernière position des séries.

    Returns:
        Les événements ordonnés par position, indicateur et nom d'événement.
    """
    events: list[IndicatorEvent] = []

    if rsi_series is not None:
        events.extend(
            detect_rsi_events(
                rsi_series,
                oversold_level=rsi_oversold_level,
                overbought_level=rsi_overbought_level,
                only_last=only_last,
            )
        )

    if ema_fast is not None and ema_slow is not None:
        events.extend(
            detect_moving_average_events(
                ema_fast,
                ema_slow,
                family="ema",
                only_last=only_last,
            )
        )

    if macd_data is not None:
        events.extend(
            detect_macd_events(
                macd_data,
                only_last=only_last,
            )
        )

    if close_series is not None and bollinger_bands is not None:
        events.extend(
            detect_bollinger_events(
                close_series,
                bollinger_bands,
                only_last=only_last,
            )
        )

    if stochastic_data is not None:
        events.extend(
            detect_stochastic_events(
                stochastic_data,
                oversold_level=stochastic_oversold_level,
                overbought_level=stochastic_overbought_level,
                only_last=only_last,
            )
        )

    atr_data = (extended_data or {}).get("atr")
    if atr_data is not None:
        events.extend(
            detect_atr_events(
                atr_data,
                only_last=only_last,
            )
        )

    adx_data = (extended_data or {}).get("adx")
    if adx_data is not None:
        events.extend(
            detect_adx_events(
                adx_data,
                weak_threshold=adx_weak_threshold,
                only_last=only_last,
            )
        )

    donchian_data = (extended_data or {}).get("donchian")
    if close_series is not None and donchian_data is not None:
        events.extend(
            detect_donchian_events(
                donchian_data,
                close_series,
                only_last=only_last,
            )
        )

    keltner_data = (extended_data or {}).get("keltner")
    if close_series is not None and keltner_data is not None:
        events.extend(
            detect_keltner_events(
                keltner_data,
                close_series,
                only_last=only_last,
            )
        )

    supertrend_data = (extended_data or {}).get("supertrend")
    if supertrend_data is not None:
        events.extend(
            detect_supertrend_events(
                supertrend_data,
                only_last=only_last,
            )
        )

    return sorted(
        events,
        key=lambda event: (
            event["position"],
            event["indicator"],
            event["event"],
        ),
    )


def build_indicator_signals(
    *,
    close: pd.Series,
    rsi_series: pd.Series | float | None = None,
    use_rsi: bool = True,
    sma_fast: pd.Series | None = None,
    sma_slow: pd.Series | None = None,
    use_sma: bool = False,
    ema_fast: pd.Series | None = None,
    ema_slow: pd.Series | None = None,
    use_ema: bool = False,
    macd_data: dict[str, pd.Series] | None = None,
    use_macd: bool = True,
    bollinger_bands: dict[str, pd.Series] | None = None,
    use_bollinger: bool = True,
    stochastic_data: dict[str, pd.Series] | None = None,
    use_stochastic: bool = True,
    stochastic_oversold: float = 20,
    stochastic_overbought: float = 80,
    extended_signals: dict[str, IndicatorSignal] | None = None,
) -> dict[str, IndicatorSignal]:
    """Construit les ``IndicatorSignal`` disponibles à partir des séries calculées.

    Chaque section n'est incluse dans le résultat que si son flag ``use_*``
    est vrai; ``sma``/``ema`` exigent en plus une série rapide non ``None``.
    Les séries doivent déjà être calculées par l'appelant (ce module ne fait
    aucun calcul d'indicateur, seulement la construction du signal structuré).
    """
    signals: dict[str, IndicatorSignal] = {}

    if use_rsi:
        signals["rsi"] = detect_rsi_signal(rsi_series)

    if use_sma and sma_fast is not None:
        signals["sma"] = detect_moving_average_signal(close, sma_fast, sma_slow, family="sma")

    if use_ema and ema_fast is not None:
        signals["ema"] = detect_moving_average_signal(close, ema_fast, ema_slow, family="ema")

    if use_macd:
        signals["macd"] = (
            build_macd_signal(macd_data)
            if macd_data is not None
            else _unavailable_signal("insufficient_data", "Historique de MACD insuffisant")
        )

    if use_bollinger:
        signals["bollinger"] = (
            build_bollinger_signal(close, bollinger_bands)
            if bollinger_bands is not None
            else _unavailable_signal("insufficient_data", "Historique de Bollinger insuffisant")
        )

    if use_stochastic:
        if stochastic_data is None:
            signals["stochastic"] = _unavailable_signal(
                "insufficient_data", "Historique de stochastique insuffisant"
            )
        else:
            valid_rows = pd.concat(
                [stochastic_data["k"].rename("k"), stochastic_data["d"].rename("d")], axis=1
            ).dropna()
            if len(valid_rows) < 2:
                signals["stochastic"] = _unavailable_signal(
                    "insufficient_data", "Historique de stochastique insuffisant"
                )
            else:
                signals["stochastic"] = build_stochastic_signal(
                    stochastic_data, stochastic_oversold, stochastic_overbought
                )

    if extended_signals:
        signals.update(extended_signals)

    return signals
