"""Calcule les limites OHLCV minimales requises par les indicateurs actifs."""

from __future__ import annotations

from app.core.settings import ScanConfig


def primary_ohlcv_limit(config: ScanConfig, *, margin: int = 10) -> int:
    """Détermine le plus grand historique requis sur le timeframe principal.

    Args:
        config: Configuration du scan.
        margin: Bougies supplémentaires demandées pour stabiliser les calculs.
    """
    requirements = [config.min_ohlcv_bars]
    if config.use_rsi:
        requirements.append(config.rsi_period + margin)
    if config.use_macd:
        requirements.append(config.macd_slow_period + config.macd_signal_period + margin)
    if config.use_bollinger:
        requirements.append(config.bollinger_period + margin)
    if config.use_stochastic:
        requirements.append(config.stochastic_k_period + config.stochastic_d_period + margin)
    if config.atr is not None and config.atr.enabled:
        requirements.append(config.atr.period + 1 + margin)
    if config.adx is not None and config.adx.enabled:
        requirements.append(2 * config.adx.period - 1 + margin)
    if config.supertrend is not None and config.supertrend.enabled:
        requirements.append(config.supertrend.atr_period + margin)
    if config.donchian is not None and config.donchian.enabled:
        requirements.append(config.donchian.period + 1 + margin)
    if config.keltner is not None and config.keltner.enabled:
        requirements.append(max(config.keltner.ema_period, config.keltner.atr_period) + 1 + margin)
    if config.use_ma and config.timeframe in config.ma_timeframes:
        requirements.append(ma_ohlcv_limit(config, margin=margin))
    return max(requirements)


def ma_ohlcv_limit(config: ScanConfig, *, margin: int = 10) -> int:
    """Détermine l'historique requis par la plus longue moyenne mobile active."""
    periods = []
    if config.use_ma and config.use_sma:
        periods.extend(config.sma_periods)
    if config.use_ma and config.use_ema:
        periods.extend(config.ema_periods)
    return max(periods, default=0) + margin
