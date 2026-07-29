from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from app.core.settings import MarketIndicatorConfig, ScanConfig
from app.domain.indicators import calculate_confluence_score, detect_trend
from app.services.market_stream import (
    calculate_indicator_bundle,
    calculate_market_snapshot,
    calculate_market_snapshots,
)
from app.services.scanner import ScannerService


@pytest.mark.parametrize(
    ("price", "sma", "ema", "expected"),
    [
        (12, (11, 10), (11, 10), "bullish"),
        (8, (9, 10), (9, 10), "bearish"),
        (12, (11, 10), (9, 10), "neutral"),
        (12, (9, 10), (11, 10), "neutral"),
        (12, (11, 10), (10, 10), "neutral"),
        (12, (10, 10), (11, 10), "neutral"),
        (8, (9, 10), (10, 10), "neutral"),
        (8, (10, 10), (9, 10), "neutral"),
        (10, (10, 10), (10, 10), "neutral"),
        (12, (11, 10), (None, None), "bullish"),
        (8, (None, None), (9, 10), "bearish"),
        (10, (None, None), (None, None), "unavailable"),
    ],
)
def test_trend_four_state_rule(price, sma, ema, expected) -> None:
    assert detect_trend(pd.Series([price]), *sma, *ema) == expected


def test_market_profile_defaults_custom_validation_and_scan_derivation() -> None:
    assert MarketIndicatorConfig().origin == "default"
    custom = MarketIndicatorConfig(rsi_period=7, sma_periods=[5, 8], origin="custom")
    assert custom.rsi_period == 7
    assert custom.sma_periods == [5, 8]
    scan = ScanConfig(rsi_period=9, sma_periods=[7, 21])
    derived = MarketIndicatorConfig.from_scan(scan)
    assert (derived.rsi_period, derived.sma_periods, derived.origin) == (9, [7, 21], "scan")
    with pytest.raises(ValidationError):
        MarketIndicatorConfig(macd_fast_period=30, macd_slow_period=20)


def test_neutral_is_available_but_short_history_is_not() -> None:
    profile = MarketIndicatorConfig(
        use_rsi=False,
        use_ma=False,
        use_bollinger=False,
        use_stochastic=False,
        confluence_weights={"macd": 20},
    )
    frame = pd.DataFrame({"timestamp": [0, 1_000], "close": [10.0, 10.0]})
    bundle = {
        "macd": {
            "macd": pd.Series([0.0, 0.0]),
            "signal": pd.Series([0.0, 0.0]),
            "histogram": pd.Series([0.0, 0.0]),
        }
    }
    neutral = calculate_market_snapshot(frame, bundle, profile)
    assert neutral["macd"] == "neutral"
    assert neutral["availability"]["macd"] == "available"
    assert neutral["confluence"]["score"] == 40

    short_frame, short_bundle = calculate_indicator_bundle([[0, 1, 2, 0, 1, 1]], profile)
    unavailable = calculate_market_snapshot(short_frame, short_bundle, profile)
    assert unavailable["macd"] is None
    assert unavailable["availability"]["macd"] == "insufficient_data"
    assert unavailable["confluence"] is None


def test_constant_bollinger_and_stochastic_are_explicitly_invalid() -> None:
    rows = [[index * 3_600_000, 5, 5, 5, 5, 1] for index in range(80)]
    frame, bundle = calculate_indicator_bundle(rows)
    snapshot = calculate_market_snapshot(frame, bundle)
    assert snapshot["availability"]["bollinger"] == "invalid_data"
    assert snapshot["availability"]["stochastic"] == "invalid_data"
    assert snapshot["bollinger"] is None
    assert snapshot["stochastic"] is None


def test_scanner_matches_market_invalid_constant_indicators() -> None:
    rows = [[index * 3_600_000, 5, 5, 5, 5, 1] for index in range(80)]
    frame, bundle = calculate_indicator_bundle(rows)
    market = calculate_market_snapshot(frame, bundle)
    scanner = ScannerService(
        ScanConfig(
            timeframe="1h",
            ma_timeframes=["1h"],
            min_trend_score=0,
            min_confluence_score=0,
        )
    )
    values = scanner._analyze_multi_indicators(frame)
    bollinger_invalid = values.pop("_bollinger_invalid", False)
    stochastic_invalid = values.pop("_stochastic_invalid", False)

    assert market["availability"]["bollinger"] == "invalid_data"
    assert market["availability"]["stochastic"] == "invalid_data"
    assert values.get("bb_position") is None
    assert values.get("stoch_signal") is None
    assert bollinger_invalid is True
    assert stochastic_invalid is True


def test_unavailable_factors_are_excluded_and_weights_renormalized() -> None:
    result = calculate_confluence_score(
        rsi_value=20,
        rsi_threshold=35,
        trend_score=None,
        max_trend_score=0,
        macd_signal=None,
        bb_position=None,
        stoch_signal=None,
        weights={"rsi": 20, "macd": 20},
        availability={"rsi": "available", "macd": "insufficient_data"},
    )
    assert result["score"] == 100
    assert result["effective_weights"] == {"rsi": 100.0}
    assert result["details"]["macd"]["contribution"] is None


def test_confirmed_snapshot_is_stable_while_provisional_changes_then_closes() -> None:
    rows = [[index * 3_600_000, 100, 102, 99, 100 + index % 7, 1] for index in range(81)]
    now_ms = 80 * 3_600_000 + 1_800_000
    first = calculate_market_snapshots(rows, "1h", now_ms=now_ms)
    changed = [list(row) for row in rows]
    changed[-1][4] += 20
    second = calculate_market_snapshots(changed, "1h", now_ms=now_ms)
    assert first["confirmed"] == second["confirmed"]
    assert first["provisional"] != second["provisional"]
    assert second["provisional"]["is_forming"] is True

    closed = calculate_market_snapshots(changed, "1h", now_ms=81 * 3_600_000)
    assert closed["provisional"] is None
    assert closed["confirmed"]["timestamp"] == 80 * 3_600


def test_scanner_and_market_use_same_profile_for_indicator_values() -> None:
    close = [100 + (index % 9) - (index % 4) for index in range(100)]
    frame = pd.DataFrame(
        {
            "timestamp": [index * 3_600_000 for index in range(100)],
            "time": pd.to_datetime(
                [index * 3_600_000 for index in range(100)], unit="ms", utc=True
            ),
            "open": close,
            "high": [value + 2 for value in close],
            "low": [value - 2 for value in close],
            "close": close,
            "volume": [1.0] * 100,
        }
    )
    config = ScanConfig(
        timeframe="1h",
        ma_timeframes=["1h"],
        min_trend_score=0,
        rsi_period=7,
        sma_periods=[5, 12],
        ema_periods=[6, 13],
        macd_fast_period=5,
        macd_slow_period=11,
        macd_signal_period=4,
        bollinger_period=10,
        stochastic_k_period=8,
        stochastic_d_period=3,
    )
    profile = MarketIndicatorConfig.from_scan(config)
    scanner_values = ScannerService(config)._analyze_multi_indicators(frame)
    market_frame, market_bundle = calculate_indicator_bundle(
        frame[["timestamp", "open", "high", "low", "close", "volume"]].values.tolist(),
        profile,
    )
    market = calculate_market_snapshot(market_frame, market_bundle, profile)
    assert scanner_values["macd_signal_type"] == market["macd"]
    assert scanner_values["bb_position"] == market["bollinger"]
    assert scanner_values["stoch_signal"] == market["stochastic"]
    assert scanner_values["macd"] == pytest.approx(
        float(market_bundle["macd"]["macd"].dropna().iloc[-1]), abs=1e-9
    )
