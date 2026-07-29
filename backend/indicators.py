"""Réexports de compatibilité pour l'ancien module public ``indicators``.

Le nouveau code doit importer ces fonctions depuis :mod:`app.domain.indicators`.
"""

from app.domain.indicators import (
    calculate_bollinger_bands,
    calculate_confluence_score,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
    check_signal_filters,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_stochastic_signal,
    detect_trend,
    get_latest_rsi,
)

__all__ = [
    "calculate_rsi",
    "get_latest_rsi",
    "calculate_sma",
    "calculate_ema",
    "detect_trend",
    "calculate_macd",
    "detect_macd_signal",
    "calculate_bollinger_bands",
    "detect_bollinger_signal",
    "calculate_stochastic",
    "detect_stochastic_signal",
    "check_signal_filters",
    "calculate_confluence_score",
]
