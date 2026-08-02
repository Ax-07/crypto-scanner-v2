"""Tests du builder commun ``build_indicator_signals`` (Phase 4)."""

from __future__ import annotations

import pandas as pd

from app.domain.indicator_bundle import build_indicator_events, build_indicator_signals
from app.domain.indicators import (
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
)


def _close_series(n: int = 80, start: float = 100.0, step: float = 0.5) -> pd.Series:
    return pd.Series([start + i * step for i in range(n)], dtype=float)


def _high_low(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    return close + 1.0, close - 1.0


def test_disabled_indicators_are_absent_not_unavailable() -> None:
    close = _close_series()
    signals = build_indicator_signals(
        close=close,
        rsi_series=None,
        use_rsi=False,
        macd_data=None,
        use_macd=False,
        bollinger_bands=None,
        use_bollinger=False,
        stochastic_data=None,
        use_stochastic=False,
    )
    assert signals == {}


def test_enabled_indicators_with_sufficient_history_are_available() -> None:
    close = _close_series()
    high, low = _high_low(close)
    rsi_series = calculate_rsi(close, 14)
    macd_data = calculate_macd(close)
    bands = calculate_bollinger_bands(close)
    stochastic_data = calculate_stochastic(high, low, close)

    signals = build_indicator_signals(
        close=close,
        rsi_series=rsi_series,
        use_rsi=True,
        macd_data=macd_data,
        use_macd=True,
        bollinger_bands=bands,
        use_bollinger=True,
        stochastic_data=stochastic_data,
        use_stochastic=True,
    )
    assert set(signals) == {"rsi", "macd", "bollinger", "stochastic"}
    for name, signal in signals.items():
        assert signal["status"] == "available", f"{name} should be available"
        assert signal.get("raw_value") is not None


def test_sma_ema_only_included_when_fast_series_provided() -> None:
    close = _close_series()
    sma_fast = calculate_sma(close, 5)
    sma_slow = calculate_sma(close, 10)

    signals = build_indicator_signals(
        close=close,
        use_rsi=False,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=False,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        use_sma=True,
    )
    assert "sma" in signals
    assert "ema" not in signals

    signals_disabled = build_indicator_signals(
        close=close,
        use_rsi=False,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=False,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        use_sma=False,
    )
    assert "sma" not in signals_disabled


def test_ema_included_when_fast_series_provided() -> None:
    close = _close_series()
    ema_fast = calculate_ema(close, 5)
    ema_slow = calculate_ema(close, 10)

    signals = build_indicator_signals(
        close=close,
        use_rsi=False,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=False,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        use_ema=True,
    )
    assert "ema" in signals


def test_missing_series_yields_insufficient_data_status() -> None:
    close = _close_series(n=3)
    signals = build_indicator_signals(
        close=close,
        rsi_series=None,
        use_rsi=True,
        macd_data=None,
        use_macd=True,
        bollinger_bands=None,
        use_bollinger=True,
        stochastic_data=None,
        use_stochastic=True,
    )
    assert set(signals) == {"rsi", "macd", "bollinger", "stochastic"}
    for signal in signals.values():
        assert signal["status"] == "insufficient_data"


def test_stochastic_single_valid_row_is_treated_as_insufficient_for_parity() -> None:
    # %K/%D valides simultanément une seule fois: detect_stochastic_signal (legacy)
    # renverrait inconditionnellement "neutral" (participation), alors que
    # build_stochastic_signal classerait la zone réelle. Le builder préserve la
    # parité stricte en refusant de faire participer l'indicateur ce tour-ci.
    k = pd.Series([None, 10.0], dtype=float)
    d = pd.Series([None, 5.0], dtype=float)
    close = _close_series(n=2)
    signals = build_indicator_signals(
        close=close,
        use_rsi=False,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=True,
        stochastic_data={"k": k, "d": d},
    )
    assert signals["stochastic"]["status"] == "insufficient_data"


def test_stochastic_at_least_two_valid_rows_is_available() -> None:
    k = pd.Series([15.0, 10.0], dtype=float)
    d = pd.Series([12.0, 5.0], dtype=float)
    close = _close_series(n=2)
    signals = build_indicator_signals(
        close=close,
        use_rsi=False,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=True,
        stochastic_data={"k": k, "d": d},
    )
    assert signals["stochastic"]["status"] == "available"


def test_build_indicator_events_aggregates_supertrend_flips() -> None:
    extended_data = {
        "supertrend": {
            "trend": pd.Series([-1.0, -1.0, 1.0, 1.0, -1.0]),
            "input_valid": pd.Series([True, True, True, True, True]),
        }
    }

    events = build_indicator_events(
        extended_data=extended_data,
    )

    assert [event["position"] for event in events] == [2, 4]
    assert [event["event"] for event in events] == [
        "bullish_flip",
        "bearish_flip",
    ]
    assert all(event["indicator"] == "supertrend" for event in events)