"""Calculs d'indicateurs purs utilisés par le scanner et le flux marché.

Le module ne dépend ni de FastAPI ni de CCXT. Les règles de confluence sont
détaillées dans ``docs/backend/confluence.md``.

Ce package façade ré-exporte les fonctions et types de chaque sous-module
(``rsi``, ``moving_averages``, ``macd``, ``bollinger``, ``stochastic``,
``confluence``) afin de préserver l'API publique historique
``app.domain.indicators``.

Chaque indicateur expose désormais, en complément de ses fonctions de
classification historiques (``detect_*_signal``), une fonction produisant un
:class:`~app.domain.indicators.types.IndicatorSignal` structuré et commun
(``detect_rsi_signal``, ``detect_moving_average_signal``,
``build_macd_signal``, ``build_bollinger_signal``,
``build_stochastic_signal``). Ces signaux structurés viennent compléter
l'API historique sans la remplacer.

``calculate_confluence_score`` accepte désormais un paramètre optionnel
``indicator_signals`` consommant directement ces ``IndicatorSignal``
structurés (mode structuré), en plus de ses arguments historiques (mode
historique, inchangé). ``check_signal_filters`` continue d'utiliser
exclusivement les types historiques.
"""

from __future__ import annotations

from app.domain.indicators.adx import build_adx_signal, calculate_adx_dmi
from app.domain.indicators.atr import build_atr_signal, calculate_atr, calculate_natr
from app.domain.indicators.bollinger import (
    build_bollinger_signal,
    calculate_bollinger_band_width,
    calculate_bollinger_bands,
    detect_bollinger_signal,
    is_bollinger_degenerate,
)
from app.domain.indicators.confluence import (
    calculate_confluence_score,
    calculate_signal_factor,
    calculate_rsi_signal_factor,
    calculate_trend_signal_factor,
    check_signal_filters,
)
from app.domain.indicators.macd import build_macd_signal, calculate_macd, detect_macd_signal
from app.domain.indicators.moving_averages import (
    calculate_ema,
    calculate_sma,
    detect_moving_average_signal,
    detect_trend,
)
from app.domain.indicators.rsi import calculate_rsi, detect_rsi_signal, get_latest_rsi
from app.domain.indicators.stochastic import (
    build_stochastic_signal,
    calculate_stochastic,
    detect_stochastic_signal,
)
from app.domain.indicators.donchian import build_donchian_signal, calculate_donchian_channels
from app.domain.indicators.keltner import build_keltner_signal, calculate_keltner_channels
from app.domain.indicators.supertrend import build_supertrend_signal, calculate_supertrend
from app.domain.indicators.types import (
    Availability,
    BollingerPosition,
    ConfluenceGrade,
    IndicatorComponent,
    IndicatorComponentUnit,
    IndicatorName,
    IndicatorSignal,
    IndicatorSignals,
    MacdSignal,
    SignalDirection,
    SignalEvent,
    StochasticSignal,
    TrendState,
)
from app.domain.indicators.wilder import (
    calculate_directional_movement,
    calculate_true_range,
    wilder_smoothing,
)

__all__ = [
    "calculate_rsi",
    "calculate_true_range",
    "calculate_directional_movement",
    "wilder_smoothing",
    "calculate_atr",
    "calculate_natr",
    "build_atr_signal",
    "calculate_adx_dmi",
    "build_adx_signal",
    "calculate_supertrend",
    "build_supertrend_signal",
    "get_latest_rsi",
    "detect_rsi_signal",
    "calculate_sma",
    "calculate_ema",
    "detect_trend",
    "detect_moving_average_signal",
    "calculate_macd",
    "detect_macd_signal",
    "build_macd_signal",
    "calculate_bollinger_bands",
    "calculate_bollinger_band_width",
    "detect_bollinger_signal",
    "is_bollinger_degenerate",
    "build_bollinger_signal",
    "calculate_donchian_channels",
    "build_donchian_signal",
    "calculate_keltner_channels",
    "build_keltner_signal",
    "calculate_stochastic",
    "detect_stochastic_signal",
    "build_stochastic_signal",
    "check_signal_filters",
    "calculate_confluence_score",
    "calculate_signal_factor",
    "calculate_rsi_signal_factor",
    "calculate_trend_signal_factor",
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
    "IndicatorComponent",
    "IndicatorComponentUnit",
]
