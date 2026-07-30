"""Orchestration du flux de marché temps réel et des données du graphique."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import deque
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypedDict, cast

import ccxt.pro as ccxtpro
import pandas as pd
from fastapi import WebSocket, WebSocketDisconnect

from app.core.settings import MarketIndicatorConfig
from app.domain.candles import candle_from_ohlcv, is_candle_closed, timeframe_seconds
from app.domain.indicator_bundle import (
    build_indicator_signals,
    calculate_extended_indicator_bundle,
)
from app.domain.indicators import (
    calculate_bollinger_bands,
    calculate_confluence_score,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_stochastic_signal,
    detect_trend,
)
from app.repositories.candle_repository import CandleRepository
from app.services.candle_sync import CandleSyncService

if TYPE_CHECKING:
    from app.services.shadow_evaluation import ShadowEvaluationService

logger = logging.getLogger(__name__)

SYMBOL = os.getenv("BINANCE_SYMBOL", "BTC/USDC")
TIMEFRAME = os.getenv("BINANCE_TIMEFRAME", "1h")
CALCULATION_LIMIT = int(os.getenv("CALCULATION_LIMIT", "500"))
DISPLAY_LIMIT = int(os.getenv("DISPLAY_LIMIT", "500"))

# Ces seuils sont lus au chargement du module afin que chaque connexion partage
# une politique de confirmation de pivots cohérente.
DIVERGENCE_LEFT = int(os.getenv("DIVERGENCE_LEFT", "3"))
DIVERGENCE_RIGHT = int(os.getenv("DIVERGENCE_RIGHT", "3"))
DIVERGENCE_MIN_BARS = int(os.getenv("DIVERGENCE_MIN_BARS", "5"))
DIVERGENCE_MAX_BARS = int(os.getenv("DIVERGENCE_MAX_BARS", "60"))
DIVERGENCE_PRICE_MIN_CHANGE = float(os.getenv("DIVERGENCE_PRICE_MIN_CHANGE", "0.001"))
INCLUDE_HIDDEN_DIVERGENCES = os.getenv("INCLUDE_HIDDEN_DIVERGENCES", "true").lower() == "true"

CALCULATION_LIMIT = max(CALCULATION_LIMIT, DISPLAY_LIMIT, 100)

MarkerPosition: TypeAlias = Literal["aboveBar", "belowBar", "inBar"]
MarkerShape: TypeAlias = Literal["circle", "square", "arrowUp", "arrowDown"]
MarkerCategory: TypeAlias = Literal["signal", "divergence"]
DivergenceSource: TypeAlias = Literal["RSI", "MACD"]
DivergenceType: TypeAlias = Literal[
    "regular_bullish", "regular_bearish", "hidden_bullish", "hidden_bearish"
]


class MarketMarker(TypedDict, total=False):
    time: int
    position: MarkerPosition
    shape: MarkerShape
    color: str
    text: str
    category: MarkerCategory
    source: DivergenceSource
    divergence_type: DivergenceType
    first_time: int
    first_price: float
    second_price: float
    first_indicator: float
    second_indicator: float


def select_closed_ohlcv(
    history: list[list[Any]],
    timeframe: str,
    *,
    now_ms: int | None = None,
) -> list[list[Any]]:
    """Sélectionne chaque bougie dont l'intervalle est explicitement terminé."""
    current_ms = int(time.time() * 1_000) if now_ms is None else now_ms
    closed: list[list[Any]] = []
    for row in history:
        if not row:
            continue
        try:
            open_time = int(float(row[0]))
        except (TypeError, ValueError, OverflowError):
            continue
        if is_candle_closed(open_time, timeframe, current_ms):
            closed.append(row)
    return closed


def normalize_candle(ohlcv: list[Any]) -> dict[str, float | int]:
    """Convertit une ligne OHLCV CCXT en bougie JSON pour le graphique.

    Le timestamp passe explicitement des millisecondes CCXT aux secondes.
    """
    timestamp, open_, high, low, close, volume = ohlcv[:6]
    return {
        "time": int(timestamp / 1000),
        "open": float(open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume or 0),
    }


def candles_to_dataframe(candles: list[list[Any]]) -> pd.DataFrame:
    """Normalise les valeurs numériques et retire les lignes OHLC invalides."""
    dataframe = pd.DataFrame(
        candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    for column in dataframe.columns:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    return dataframe.dropna(subset=["timestamp", "open", "high", "low", "close"]).reset_index(
        drop=True
    )


def last_finite_value(series: pd.Series | None) -> float | None:
    """Extrait la dernière valeur finie d'une série, ou ``None``."""
    if series is None:
        return None

    clean = series.dropna()
    if clean.empty:
        return None

    value = float(clean.iloc[-1])
    return value if math.isfinite(value) else None


def series_to_chart_points(
    timestamps: pd.Series,
    values: pd.Series | None,
    limit: int | None = DISPLAY_LIMIT,
) -> list[dict[str, float | int]]:
    """Convertit une série en points ``time``/``value`` bornés pour le graphique."""
    if values is None:
        return []

    points: list[dict[str, float | int]] = []

    for timestamp, value in zip(timestamps, values):
        if pd.isna(timestamp) or pd.isna(value):
            continue

        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            continue

        points.append(
            {
                "time": int(float(timestamp) / 1000),
                "value": numeric_value,
            }
        )

    return points[-limit:] if limit is not None else points


def calculate_indicator_bundle(
    candles: list[list[Any]],
    profile: MarketIndicatorConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Calcule les indicateurs actifs du profil partagé."""
    profile = profile or MarketIndicatorConfig()
    dataframe = candles_to_dataframe(candles)

    if dataframe.empty:
        return dataframe, {}

    close = dataframe["close"].reset_index(drop=True)
    high = dataframe["high"].reset_index(drop=True)
    low = dataframe["low"].reset_index(drop=True)

    bundle: dict[str, Any] = {}
    if profile.use_rsi:
        bundle["rsi"] = calculate_rsi(close, period=profile.rsi_period)
        bundle[f"rsi_{profile.rsi_period}"] = bundle["rsi"]
        bundle["rsi_14"] = bundle["rsi"]
    if profile.use_ma and profile.use_sma:
        for period in profile.sma_periods:
            bundle[f"sma_{period}"] = calculate_sma(close, period=period)
    if profile.use_ma and profile.use_ema:
        for period in profile.ema_periods:
            bundle[f"ema_{period}"] = calculate_ema(close, period=period)
        bundle["_ema_fast"] = bundle[f"ema_{profile.ema_periods[0]}"]
        bundle["_ema_slow"] = (
            bundle[f"ema_{profile.ema_periods[1]}"] if len(profile.ema_periods) > 1 else None
        )
    if profile.use_macd:
        bundle["macd"] = calculate_macd(
            close,
            fast_period=profile.macd_fast_period,
            slow_period=profile.macd_slow_period,
            signal_period=profile.macd_signal_period,
        )
    if profile.use_bollinger:
        bundle["bollinger"] = calculate_bollinger_bands(
            close,
            period=profile.bollinger_period,
            std_dev=profile.bollinger_std_dev,
        )
    if profile.use_stochastic:
        bundle["stochastic"] = calculate_stochastic(
            high=high,
            low=low,
            close=close,
            k_period=profile.stochastic_k_period,
            d_period=profile.stochastic_d_period,
        )
    atr_config = profile.atr
    adx_config = profile.adx
    supertrend_config = profile.supertrend
    donchian_config = profile.donchian
    keltner_config = profile.keltner
    extended_data, extended_signals = calculate_extended_indicator_bundle(
        high=high,
        low=low,
        close=close,
        use_atr=bool(atr_config and atr_config.enabled),
        atr_period=atr_config.period if atr_config else 14,
        use_adx=bool(adx_config and adx_config.enabled),
        adx_period=adx_config.period if adx_config else 14,
        adx_weak_threshold=adx_config.weak_threshold if adx_config else 20,
        adx_strong_threshold=adx_config.strong_threshold if adx_config else 25,
        use_supertrend=bool(supertrend_config and supertrend_config.enabled),
        supertrend_atr_period=supertrend_config.atr_period if supertrend_config else 10,
        supertrend_multiplier=supertrend_config.multiplier if supertrend_config else 3.0,
        use_donchian=bool(donchian_config and donchian_config.enabled),
        donchian_period=donchian_config.period if donchian_config else 20,
        use_keltner=bool(keltner_config and keltner_config.enabled),
        keltner_ema_period=keltner_config.ema_period if keltner_config else 20,
        keltner_atr_period=keltner_config.atr_period if keltner_config else 10,
        keltner_multiplier=keltner_config.multiplier if keltner_config else 2.0,
    )
    if extended_data:
        bundle["_extended_data"] = extended_data
        bundle["_extended_signals"] = extended_signals

    return dataframe, bundle


def bundle_to_chart_data(
    dataframe: pd.DataFrame,
    bundle: dict[str, Any],
    *,
    limit: int | None = DISPLAY_LIMIT,
) -> dict[str, list[dict[str, float | int]]]:
    """Convertit chaque série d'indicateur en historique compatible graphique."""
    if dataframe.empty:
        return {}

    timestamps = dataframe["timestamp"].reset_index(drop=True)

    result: dict[str, list[dict[str, float | int]]] = {
        name: series_to_chart_points(timestamps, value, limit)
        for name, value in bundle.items()
        if name != "rsi"
        and name.startswith(("rsi_", "sma_", "ema_"))
        and isinstance(value, pd.Series)
    }

    macd_data = bundle.get("macd")
    if macd_data:
        result["macd"] = series_to_chart_points(timestamps, macd_data.get("macd"), limit)
        result["macd_signal"] = series_to_chart_points(timestamps, macd_data.get("signal"), limit)
        result["macd_histogram"] = series_to_chart_points(
            timestamps, macd_data.get("histogram"), limit
        )

    bollinger_data = bundle.get("bollinger")
    if bollinger_data:
        result["bollinger_upper"] = series_to_chart_points(
            timestamps, bollinger_data.get("upper"), limit
        )
        result["bollinger_middle"] = series_to_chart_points(
            timestamps, bollinger_data.get("middle"), limit
        )
        result["bollinger_lower"] = series_to_chart_points(
            timestamps, bollinger_data.get("lower"), limit
        )

    stochastic_data = bundle.get("stochastic")
    if stochastic_data:
        result["stochastic_k"] = series_to_chart_points(timestamps, stochastic_data.get("k"), limit)
        result["stochastic_d"] = series_to_chart_points(timestamps, stochastic_data.get("d"), limit)

    return result


def indicator_last_points(
    chart_data: dict[str, list[dict[str, float | int]]],
) -> dict[str, dict[str, float | int]]:
    """Réduit les historiques d'indicateurs à leur dernier point disponible."""
    return {name: points[-1] for name, points in chart_data.items() if points}


def calculate_market_snapshot(
    dataframe: pd.DataFrame,
    bundle: dict[str, Any],
    profile: MarketIndicatorConfig | None = None,
) -> dict[str, Any]:
    """Construit une vue de signaux avec disponibilité explicite."""
    profile = profile or MarketIndicatorConfig()
    if dataframe.empty:
        availability = {
            name: "disabled" if not enabled else "insufficient_data"
            for name, enabled in {
                "rsi": profile.use_rsi,
                "trend": profile.use_ma,
                "macd": profile.use_macd,
                "bollinger": profile.use_bollinger,
                "stochastic": profile.use_stochastic,
            }.items()
        }
        return {
            "price": None,
            "timestamp": None,
            "rsi": None,
            "trend": "unavailable",
            "macd": None,
            "bollinger": None,
            "stochastic": None,
            "confluence": None,
            "availability": availability,
            "indicator_signals": {},
        }

    close = dataframe["close"].reset_index(drop=True)
    rsi_value = last_finite_value(bundle.get("rsi"))

    def ma_values(prefix: str, periods: list[int]) -> tuple[float | None, float | None]:
        values = [last_finite_value(bundle.get(f"{prefix}_{period}")) for period in periods]
        calculated = [value for value in values if value is not None]
        return (
            calculated[0] if calculated else None,
            calculated[1] if len(calculated) > 1 else None,
        )

    sma_fast, sma_slow = ma_values("sma", profile.sma_periods)
    ema_fast, ema_slow = ma_values("ema", profile.ema_periods)
    trend = detect_trend(
        close=close,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
    )

    macd_data = cast(dict[str, pd.Series] | None, bundle.get("macd"))
    macd_available = bool(
        macd_data and len(pd.concat([macd_data["macd"], macd_data["signal"]], axis=1).dropna()) >= 2
    )
    macd_signal = detect_macd_signal(macd_data) if macd_available and macd_data else None

    bollinger_data = cast(dict[str, pd.Series] | None, bundle.get("bollinger"))
    bollinger_width = (
        last_finite_value(bollinger_data["upper"] - bollinger_data["lower"])
        if bollinger_data
        else None
    )
    bollinger_available = bollinger_width is not None and bollinger_width > 0
    bollinger_signal = (
        detect_bollinger_signal(close, bollinger_data)
        if bollinger_available and bollinger_data
        else None
    )

    stochastic_data = cast(dict[str, pd.Series] | None, bundle.get("stochastic"))
    stochastic_available = bool(
        stochastic_data
        and len(pd.concat([stochastic_data["k"], stochastic_data["d"]], axis=1).dropna()) >= 2
    )
    stochastic_signal = (
        detect_stochastic_signal(
            stochastic_data,
            profile.stochastic_oversold,
            profile.stochastic_overbought,
        )
        if stochastic_available and stochastic_data
        else None
    )

    def ma_fast_slow_series(
        prefix: str, periods: list[int]
    ) -> tuple[pd.Series | None, pd.Series | None]:
        sorted_periods = sorted(periods)
        series = [bundle.get(f"{prefix}_{period}") for period in sorted_periods]
        available = [item for item in series if item is not None]
        return (
            available[0] if available else None,
            available[1] if len(available) > 1 else None,
        )

    use_sma = profile.use_ma and profile.use_sma
    use_ema = profile.use_ma and profile.use_ema
    sma_fast_series, sma_slow_series = (
        ma_fast_slow_series("sma", profile.sma_periods) if use_sma else (None, None)
    )
    ema_fast_series, ema_slow_series = (
        ma_fast_slow_series("ema", profile.ema_periods) if use_ema else (None, None)
    )
    # market_stream est mono-timeframe: contrairement au moteur canonique
    # (scanner/backtest), il construit ici des signaux structurés sma/ema en
    # plus de rsi/macd/bollinger/stochastic. Ces clés sma/ema sont exposées
    # dans "indicator_signals" pour information, mais volontairement exclues
    # de l'appel à calculate_confluence_score ci-dessous: le facteur de
    # tendance structuré (calculate_trend_signal_factor, moyenne simple des
    # facteurs sma/ema) diverge subtilement de detect_trend()/trend_states
    # (règle de majorité/alignement) près des cas limites. Le score de
    # confluence continue donc d'utiliser le mode historique pour la
    # tendance, comme avant ce câblage.
    indicator_signals = build_indicator_signals(
        close=close,
        rsi_series=bundle.get("rsi"),
        use_rsi=profile.use_rsi,
        sma_fast=sma_fast_series,
        sma_slow=sma_slow_series,
        use_sma=use_sma,
        ema_fast=ema_fast_series,
        ema_slow=ema_slow_series,
        use_ema=use_ema,
        macd_data=macd_data,
        use_macd=profile.use_macd,
        bollinger_bands=bollinger_data,
        use_bollinger=profile.use_bollinger,
        stochastic_data=stochastic_data,
        use_stochastic=profile.use_stochastic,
        stochastic_oversold=profile.stochastic_oversold,
        stochastic_overbought=profile.stochastic_overbought,
        extended_signals=cast(
            dict[str, Any] | None,
            bundle.get("_extended_signals"),
        ),
    )
    availability = {
        "rsi": (
            "disabled"
            if not profile.use_rsi
            else "available" if rsi_value is not None else "insufficient_data"
        ),
        "trend": (
            "disabled"
            if not profile.use_ma
            else "available" if trend != "unavailable" else "insufficient_data"
        ),
        "macd": (
            "disabled"
            if not profile.use_macd
            else "available" if macd_available else "insufficient_data"
        ),
        "bollinger": (
            "disabled"
            if not profile.use_bollinger
            else (
                "available"
                if bollinger_available
                else "invalid_data" if bollinger_width == 0 else "insufficient_data"
            )
        ),
        "stochastic": (
            "disabled"
            if not profile.use_stochastic
            else (
                "available"
                if stochastic_available
                else (
                    "invalid_data"
                    if stochastic_data is not None and stochastic_data["k"].isna().all()
                    else "insufficient_data"
                )
            )
        ),
    }
    availability.update(
        {
            name: signal["status"]
            for name, signal in indicator_signals.items()
            if name in {"atr", "adx", "supertrend", "donchian", "keltner"}
        }
    )

    confluence = calculate_confluence_score(
        rsi_value=rsi_value,
        rsi_threshold=profile.rsi_threshold,
        trend_score=None,
        max_trend_score=1,
        macd_signal=macd_signal,
        bb_position=bollinger_signal,
        stoch_signal=stochastic_signal,
        weights=profile.confluence_weights if profile.use_confluence_score else {},
        trend_states=[trend],
        availability=cast(dict[str, Any], availability),
        raw_values={
            "rsi": rsi_value,
            "trend_signal": trend,
            "macd_signal": macd_signal,
            "bollinger_signal": bollinger_signal,
            "stochastic_signal": stochastic_signal,
        },
        indicator_signals={
            name: signal
            for name, signal in indicator_signals.items()
            if name in {"rsi", "macd", "bollinger", "stochastic"}
        },
    )

    return {
        "price": float(close.iloc[-1]),
        "timestamp": int(float(dataframe["timestamp"].iloc[-1]) / 1000),
        "rsi": rsi_value,
        "trend": trend,
        "macd": macd_signal,
        "bollinger": bollinger_signal,
        "stochastic": stochastic_signal,
        "confluence": confluence,
        "availability": availability,
        "indicator_signals": indicator_signals,
    }


def calculate_market_snapshots(
    history: list[list[Any]],
    timeframe: str,
    profile: MarketIndicatorConfig | None = None,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Produit les vues confirmée/provisoire et les anciens champs dérivés."""
    profile = profile or MarketIndicatorConfig()
    closed = select_closed_ohlcv(history, timeframe, now_ms=now_ms)
    closed_frame, closed_bundle = calculate_indicator_bundle(closed, profile)
    confirmed = calculate_market_snapshot(closed_frame, closed_bundle, profile)
    provisional = None
    if history and len(closed) < len(history):
        full_frame, full_bundle = calculate_indicator_bundle(history, profile)
        provisional = calculate_market_snapshot(full_frame, full_bundle, profile)
        provisional["is_forming"] = True
    legacy = provisional or confirmed
    return {
        **legacy,
        "confirmed": confirmed,
        "provisional": provisional,
        "profile": profile.model_dump(mode="json"),
    }


def build_crossover_markers(
    dataframe: pd.DataFrame,
    bundle: dict[str, Any],
    minimum_time: int | None = None,
    only_last_candle: bool = False,
) -> list[dict[str, Any]]:
    """Crée les marqueurs EMA et MACD sur des bougies clôturées.

    ``only_last_candle`` limite l'évaluation au dernier index, utile lorsqu'une
    nouvelle bougie vient de confirmer la clôture précédente.
    """
    if dataframe.empty or len(dataframe) < 2:
        return []

    timestamps = dataframe["timestamp"].reset_index(drop=True)
    ema20 = bundle.get("_ema_fast", bundle.get("ema_20"))
    ema50 = bundle.get("_ema_slow", bundle.get("ema_50"))

    macd_data = bundle.get("macd")
    histogram = macd_data.get("histogram") if macd_data else None

    start_index = len(dataframe) - 1 if only_last_candle else 1
    markers: list[dict[str, Any]] = []

    for index in range(start_index, len(dataframe)):
        candle_time = int(float(timestamps.iloc[index]) / 1000)

        if minimum_time is not None and candle_time < minimum_time:
            continue

        if ema20 is not None and ema50 is not None:
            values = (
                ema20.iloc[index - 1],
                ema50.iloc[index - 1],
                ema20.iloc[index],
                ema50.iloc[index],
            )

            if all(pd.notna(value) for value in values):
                short_previous, long_previous, short_current, long_current = values

                if short_previous <= long_previous and short_current > long_current:
                    markers.append(
                        {
                            "time": candle_time,
                            "position": "belowBar",
                            "shape": "arrowUp",
                            "color": "#22c55e",
                            "text": "BUY EMA 20/50",
                            "category": "signal",
                        }
                    )
                elif short_previous >= long_previous and short_current < long_current:
                    markers.append(
                        {
                            "time": candle_time,
                            "position": "aboveBar",
                            "shape": "arrowDown",
                            "color": "#ef4444",
                            "text": "SELL EMA 20/50",
                            "category": "signal",
                        }
                    )

        if histogram is not None:
            previous_histogram = histogram.iloc[index - 1]
            current_histogram = histogram.iloc[index]

            if pd.notna(previous_histogram) and pd.notna(current_histogram):
                if previous_histogram <= 0 < current_histogram:
                    markers.append(
                        {
                            "time": candle_time,
                            "position": "belowBar",
                            "shape": "circle",
                            "color": "#38bdf8",
                            "text": "MACD haussier",
                            "category": "signal",
                        }
                    )
                elif previous_histogram >= 0 > current_histogram:
                    markers.append(
                        {
                            "time": candle_time,
                            "position": "aboveBar",
                            "shape": "circle",
                            "color": "#f59e0b",
                            "text": "MACD baissier",
                            "category": "signal",
                        }
                    )

    return markers


def find_pivots(
    series: pd.Series,
    pivot_type: str,
    left: int,
    right: int,
) -> list[int]:
    """Retourne les indices de pivots stricts confirmés à gauche et à droite."""
    pivots: list[int] = []

    for index in range(left, len(series) - right):
        center = series.iloc[index]

        if pd.isna(center):
            continue

        left_values = series.iloc[index - left : index].dropna()
        right_values = series.iloc[index + 1 : index + right + 1].dropna()

        if len(left_values) != left or len(right_values) != right:
            continue

        if pivot_type == "low":
            is_pivot = center < left_values.min() and center < right_values.min()
        else:
            is_pivot = center > left_values.max() and center > right_values.max()

        if is_pivot:
            pivots.append(index)

    return pivots


def detect_divergences(
    dataframe: pd.DataFrame,
    indicator: pd.Series | None,
    source: str,
    indicator_min_change: float,
    minimum_time: int | None = None,
    only_newly_confirmed: bool = False,
) -> list[dict[str, Any]]:
    """Détecte les divergences classiques et cachées entre prix et indicateur.

    Le second pivot est confirmé après DIVERGENCE_RIGHT bougies. En temps
    réel, only_newly_confirmed=True retourne uniquement la divergence qui
    vient d'être confirmée par la dernière bougie fermée.
    """
    if dataframe.empty or indicator is None or len(dataframe) != len(indicator):
        return []

    high = dataframe["high"].reset_index(drop=True)
    low = dataframe["low"].reset_index(drop=True)
    timestamps = dataframe["timestamp"].reset_index(drop=True)
    indicator = indicator.reset_index(drop=True)

    low_pivots = find_pivots(
        low,
        "low",
        DIVERGENCE_LEFT,
        DIVERGENCE_RIGHT,
    )
    high_pivots = find_pivots(
        high,
        "high",
        DIVERGENCE_LEFT,
        DIVERGENCE_RIGHT,
    )

    results: list[dict[str, Any]] = []

    def is_valid_pair(first_index: int, second_index: int) -> bool:
        """Valide distance et instant de confirmation d'une paire de pivots."""
        distance = second_index - first_index

        if not (DIVERGENCE_MIN_BARS <= distance <= DIVERGENCE_MAX_BARS):
            return False

        if only_newly_confirmed:
            confirmation_index = second_index + DIVERGENCE_RIGHT
            return confirmation_index == len(dataframe) - 1

        return True

    def append_marker(
        divergence_type: str,
        first_index: int,
        second_index: int,
        first_price: float,
        second_price: float,
        first_indicator: float,
        second_indicator: float,
    ) -> None:
        """Ajoute un marqueur sérialisable si sa date appartient à la fenêtre visible."""
        marker_time = int(float(timestamps.iloc[second_index]) / 1000)

        if minimum_time is not None and marker_time < minimum_time:
            return

        bullish = divergence_type.endswith("bullish")
        hidden = divergence_type.startswith("hidden")

        if source == "RSI":
            regular_color = "#a78bfa"
            hidden_color = "#c084fc"
        else:
            regular_color = "#22d3ee"
            hidden_color = "#06b6d4"

        results.append(
            {
                "time": marker_time,
                "position": "belowBar" if bullish else "aboveBar",
                "shape": ("square" if hidden else "arrowUp" if bullish else "arrowDown"),
                "color": hidden_color if hidden else regular_color,
                "text": (
                    f"{source} div. cachée " f"{'haussière' if bullish else 'baissière'}"
                    if hidden
                    else f"{source} div. " f"{'haussière' if bullish else 'baissière'}"
                ),
                "category": "divergence",
                "source": source,
                "divergence_type": divergence_type,
                "first_time": int(float(timestamps.iloc[first_index]) / 1000),
                "first_price": float(first_price),
                "second_price": float(second_price),
                "first_indicator": float(first_indicator),
                "second_indicator": float(second_indicator),
            }
        )

    for first_index, second_index in zip(low_pivots, low_pivots[1:]):
        if not is_valid_pair(first_index, second_index):
            continue

        first_price = float(low.iloc[first_index])
        second_price = float(low.iloc[second_index])
        first_indicator = indicator.iloc[first_index]
        second_indicator = indicator.iloc[second_index]

        if pd.isna(first_indicator) or pd.isna(second_indicator):
            continue

        price_change = (second_price - first_price) / first_price
        indicator_change = float(second_indicator - first_indicator)

        # Prix : creux plus bas ; indicateur : creux plus haut.
        if (
            price_change <= -DIVERGENCE_PRICE_MIN_CHANGE
            and indicator_change >= indicator_min_change
        ):
            append_marker(
                "regular_bullish",
                first_index,
                second_index,
                first_price,
                second_price,
                float(first_indicator),
                float(second_indicator),
            )

        # Prix : creux plus haut ; indicateur : creux plus bas.
        elif (
            INCLUDE_HIDDEN_DIVERGENCES
            and price_change >= DIVERGENCE_PRICE_MIN_CHANGE
            and indicator_change <= -indicator_min_change
        ):
            append_marker(
                "hidden_bullish",
                first_index,
                second_index,
                first_price,
                second_price,
                float(first_indicator),
                float(second_indicator),
            )

    for first_index, second_index in zip(high_pivots, high_pivots[1:]):
        if not is_valid_pair(first_index, second_index):
            continue

        first_price = float(high.iloc[first_index])
        second_price = float(high.iloc[second_index])
        first_indicator = indicator.iloc[first_index]
        second_indicator = indicator.iloc[second_index]

        if pd.isna(first_indicator) or pd.isna(second_indicator):
            continue

        price_change = (second_price - first_price) / first_price
        indicator_change = float(second_indicator - first_indicator)

        # Prix : sommet plus haut ; indicateur : sommet plus bas.
        if (
            price_change >= DIVERGENCE_PRICE_MIN_CHANGE
            and indicator_change <= -indicator_min_change
        ):
            append_marker(
                "regular_bearish",
                first_index,
                second_index,
                first_price,
                second_price,
                float(first_indicator),
                float(second_indicator),
            )

        # Prix : sommet plus bas ; indicateur : sommet plus haut.
        elif (
            INCLUDE_HIDDEN_DIVERGENCES
            and price_change <= -DIVERGENCE_PRICE_MIN_CHANGE
            and indicator_change >= indicator_min_change
        ):
            append_marker(
                "hidden_bearish",
                first_index,
                second_index,
                first_price,
                second_price,
                float(first_indicator),
                float(second_indicator),
            )

    return results


def build_divergence_markers(
    dataframe: pd.DataFrame,
    bundle: dict[str, Any],
    minimum_time: int | None = None,
    only_newly_confirmed: bool = False,
) -> list[dict[str, Any]]:
    """Agrège les marqueurs de divergence RSI et MACD."""
    markers: list[dict[str, Any]] = []

    markers.extend(
        detect_divergences(
            dataframe=dataframe,
            indicator=bundle.get("rsi_14"),
            source="RSI",
            indicator_min_change=2.0,
            minimum_time=minimum_time,
            only_newly_confirmed=only_newly_confirmed,
        )
    )

    macd_data = bundle.get("macd")
    macd_line = macd_data.get("macd") if macd_data else None

    markers.extend(
        detect_divergences(
            dataframe=dataframe,
            indicator=macd_line,
            source="MACD",
            indicator_min_change=0.0,
            minimum_time=minimum_time,
            only_newly_confirmed=only_newly_confirmed,
        )
    )

    return markers


def sort_markers(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trie les marqueurs par temps, catégorie puis libellé pour un ordre stable."""
    return sorted(
        markers,
        key=lambda marker: (
            marker["time"],
            marker.get("category", ""),
            marker["text"],
        ),
    )


async def wait_for_websocket_disconnect(websocket: WebSocket) -> int:
    """Attend la fermeture cliente afin de ne pas laisser un flux Binance orphelin."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return int(message.get("code", 1000))


async def watch_ohlcv_until_disconnect(
    exchange: Any,
    symbol: str,
    timeframe: str,
    disconnect_task: asyncio.Task[int],
) -> list[list[Any]]:
    """Attend Binance ou interrompt immédiatement l'attente si le navigateur part."""
    watch_task = asyncio.create_task(exchange.watch_ohlcv(symbol, timeframe))
    done, _ = await asyncio.wait(
        {watch_task, disconnect_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if disconnect_task in done:
        watch_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await watch_task
        raise WebSocketDisconnect(code=disconnect_task.result())

    return await watch_task


async def websocket_market_data(
    websocket: WebSocket,
    symbol: str = SYMBOL,
    timeframe: str = TIMEFRAME,
    *,
    repository: CandleRepository | None = None,
    candle_sync: CandleSyncService | None = None,
    include_history: bool = True,
    profile: MarketIndicatorConfig | None = None,
    shadow_evaluation: ShadowEvaluationService | None = None,
) -> None:
    """Diffuse l'historique Binance puis les mises à jour OHLCV en continu.

    La connexion est acceptée avant validation. Un message ``history`` précède
    les messages ``update``. Toute erreur applicative est envoyée sous la forme
    ``error`` lorsque la socket le permet, puis l'exchange est fermé.

    Args:
        websocket: Connexion FastAPI à accepter et alimenter.
        symbol: Symbole Binance au format CCXT, normalisé en majuscules.
        timeframe: Timeframe vérifié par le domaine des bougies.
    """
    await websocket.accept()
    profile = profile or MarketIndicatorConfig()

    symbol = symbol.strip().upper()
    timeframe = timeframe.strip()

    exchange = ccxtpro.binance(
        {
            "enableRateLimit": True,
            "newUpdates": True,
        }
    )
    disconnect_task = asyncio.create_task(wait_for_websocket_disconnect(websocket))

    candles: deque[list[Any]] = deque(maxlen=CALCULATION_LIMIT)
    last_open_write = 0.0
    stream_repository = (
        repository if candle_sync is None or candle_sync.settings.candle_storage_enabled else None
    )

    try:
        timeframe_seconds(timeframe)
        logger.info("Connexion Binance %s %s", symbol, timeframe)
        await exchange.load_markets()

        if symbol not in exchange.markets:
            raise ValueError(f"Symbole Binance inconnu : {symbol}")

        if not exchange.has.get("watchOHLCV"):
            raise RuntimeError("watch_ohlcv n'est pas disponible dans cette version de CCXT.")

        history: list[list[Any]]
        if (
            repository is not None
            and candle_sync is not None
            and candle_sync.settings.candle_storage_enabled
        ):
            try:
                await candle_sync.sync_latest(
                    exchange_id="binance",
                    market_type="spot",
                    symbol=symbol,
                    timeframe=timeframe,
                    required_bars=CALCULATION_LIMIT,
                    exchange=exchange,
                )
                stored = await repository.get_latest(
                    "binance",
                    "spot",
                    symbol,
                    timeframe,
                    CALCULATION_LIMIT,
                    closed_only=False,
                )
                history = [candle.to_ohlcv() for candle in stored]
            except Exception:
                logger.exception(
                    "Stockage local indisponible pendant le chargement de %s %s",
                    symbol,
                    timeframe,
                )
                history = await exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=CALCULATION_LIMIT,
                )
        else:
            history = await exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=CALCULATION_LIMIT,
            )

        if not history:
            raise RuntimeError("Binance n'a retourné aucune bougie OHLCV.")

        candles.extend(history)
        visible_history = history[-DISPLAY_LIMIT:]
        visible_start_time = int(visible_history[0][0] / 1000)

        full_dataframe, full_bundle = calculate_indicator_bundle(history, profile)
        indicator_history = bundle_to_chart_data(
            full_dataframe,
            full_bundle,
        )
        snapshot = calculate_market_snapshots(history, timeframe, profile)

        closed_history = select_closed_ohlcv(history, timeframe)
        closed_dataframe, closed_bundle = calculate_indicator_bundle(closed_history, profile)

        historical_markers = sort_markers(
            build_crossover_markers(
                closed_dataframe,
                closed_bundle,
                minimum_time=visible_start_time,
            )
            + build_divergence_markers(
                closed_dataframe,
                closed_bundle,
                minimum_time=visible_start_time,
            )
        )

        if include_history:
            await websocket.send_json(
                {
                    "type": "history",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "candles": [normalize_candle(candle) for candle in visible_history],
                    "indicators": indicator_history,
                    "markers": historical_markers,
                    "snapshot": snapshot,
                }
            )

        while True:
            updates = await watch_ohlcv_until_disconnect(
                exchange,
                symbol,
                timeframe,
                disconnect_task,
            )

            if not updates:
                continue

            latest = updates[-1]
            latest_timestamp = int(latest[0])
            new_markers: list[dict[str, Any]] = []

            if not candles:
                candles.append(latest)
                await _persist_stream_candle(stream_repository, latest, symbol, timeframe)
                last_open_write = time.monotonic()

            elif latest_timestamp == int(candles[-1][0]):
                # La bougie ouverte évolue.
                candles[-1] = latest
                interval = (
                    candle_sync.settings.candle_open_write_interval_seconds
                    if candle_sync is not None
                    else 5.0
                )
                if time.monotonic() - last_open_write >= interval:
                    await _persist_stream_candle(stream_repository, latest, symbol, timeframe)
                    last_open_write = time.monotonic()

            elif latest_timestamp > int(candles[-1][0]):
                # La bougie précédente vient de fermer.
                previous = list(candles[-1])
                await _persist_stream_candle(
                    stream_repository,
                    previous,
                    symbol,
                    timeframe,
                    force_closed=True,
                )
                closed_snapshot = list(candles)
                if shadow_evaluation is not None:
                    try:
                        decision_time = latest_timestamp
                        canonical_candles = [
                            candle_from_ohlcv(
                                row,
                                exchange_id="binance",
                                market_type="spot",
                                symbol=symbol,
                                timeframe=timeframe,
                                now_ms=decision_time,
                            )
                            for row in closed_snapshot
                        ]
                        await shadow_evaluation.evaluate_closed_candle(
                            symbol=symbol,
                            timeframe=timeframe,
                            candles=canonical_candles,
                        )
                    except Exception:
                        logger.exception(
                            "Évaluation shadow impossible pour %s %s",
                            symbol,
                            timeframe,
                        )
                closed_dataframe, closed_bundle = calculate_indicator_bundle(
                    closed_snapshot, profile
                )

                new_markers = sort_markers(
                    build_crossover_markers(
                        closed_dataframe,
                        closed_bundle,
                        only_last_candle=True,
                    )
                    + build_divergence_markers(
                        closed_dataframe,
                        closed_bundle,
                        only_newly_confirmed=True,
                    )
                )

                candles.append(latest)
                await _persist_stream_candle(stream_repository, latest, symbol, timeframe)
                last_open_write = time.monotonic()

            else:
                continue

            current_dataframe, current_bundle = calculate_indicator_bundle(list(candles), profile)
            current_chart_data = bundle_to_chart_data(
                current_dataframe,
                current_bundle,
            )

            await websocket.send_json(
                {
                    "type": "update",
                    "candle": normalize_candle(latest),
                    "indicators": indicator_last_points(current_chart_data),
                    "markers": new_markers,
                    "snapshot": calculate_market_snapshots(list(candles), timeframe, profile),
                }
            )

    except WebSocketDisconnect:
        logger.info("Navigateur déconnecté de %s %s", symbol, timeframe)

    except Exception as error:
        logger.exception("Erreur WebSocket")

        with suppress(Exception):
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"{type(error).__name__}: {error}",
                }
            )

    finally:
        disconnect_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await disconnect_task
        await exchange.close()
        logger.info("Connexion Binance %s %s fermée", symbol, timeframe)


async def _persist_stream_candle(
    repository: CandleRepository | None,
    row: list[Any],
    symbol: str,
    timeframe: str,
    *,
    force_closed: bool = False,
) -> None:
    """Persiste une transition du flux sans rendre une erreur SQLite fatale."""
    if repository is None:
        return
    try:
        now_ms = int(time.time() * 1_000)
        candle = candle_from_ohlcv(
            row,
            exchange_id="binance",
            market_type="spot",
            symbol=symbol,
            timeframe=timeframe,
            now_ms=now_ms,
        )
        if force_closed and not candle.is_closed:
            candle = type(candle)(
                exchange_id=candle.exchange_id,
                market_type=candle.market_type,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                open_time=candle.open_time,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                close_time=candle.close_time,
                is_closed=True,
            )
        await repository.upsert_many([candle])
    except Exception:
        logger.exception("Échec non fatal de persistance WebSocket pour %s %s", symbol, timeframe)
