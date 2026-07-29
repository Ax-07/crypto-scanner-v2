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

from app.domain.indicators.bollinger import (
    build_bollinger_signal,
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
from app.domain.indicators.types import (
    Availability,
    BollingerPosition,
    ConfluenceGrade,
    IndicatorName,
    IndicatorSignal,
    IndicatorSignals,
    MacdSignal,
    SignalDirection,
    SignalEvent,
    StochasticSignal,
    TrendState,
)

__all__ = [
    "calculate_rsi",
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
    "detect_bollinger_signal",
    "is_bollinger_degenerate",
    "build_bollinger_signal",
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
]
