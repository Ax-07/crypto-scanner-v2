from __future__ import annotations

import json
import math
from decimal import Decimal
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.settings import MarketIndicatorConfig, ScanConfig
from app.domain.backtesting import calculate_forward_outcomes, evaluate_information_set
from app.domain.indicator_bundle import calculate_extended_indicator_bundle
from app.domain.indicators import (
    build_bollinger_signal,
    build_donchian_signal,
    build_keltner_signal,
    calculate_atr,
    calculate_bollinger_band_width,
    calculate_bollinger_bands,
    calculate_donchian_channels,
    calculate_ema,
    calculate_keltner_channels,
    detect_bollinger_signal,
)
from app.domain.portfolio import PortfolioSimulationConfig, simulate_portfolio
from app.models.backtest import BacktestConfig
from app.main import app
from app.services.market_stream import calculate_indicator_bundle, calculate_market_snapshot
from app.services.portfolio_replay import build_portfolio_simulation_steps
from tests.fixtures.synthetic_backtest_v1 import candles


def series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def test_bollinger_width_reuses_bands_and_preserves_historical_verdict() -> None:
    close = series([10, 11, 12, 13, 14, 15])
    bands = calculate_bollinger_bands(close, period=3, std_dev=2)
    derived = calculate_bollinger_band_width(close, bands)
    expected_width = float(bands["upper"].iloc[-1] - bands["lower"].iloc[-1])
    assert derived["band_width"].iloc[-1] == pytest.approx(expected_width)
    assert derived["band_width_percent"].iloc[-1] == pytest.approx(
        100 * expected_width / bands["middle"].iloc[-1]
    )
    assert derived["band_position"].iloc[-1] == pytest.approx(
        (close.iloc[-1] - bands["lower"].iloc[-1]) / expected_width
    )

    signal = build_bollinger_signal(close, bands)
    assert {
        "status": signal["status"],
        "direction": signal["direction"],
        "signal": signal["signal"],
        "state": signal["state"],
        "strength": signal["strength"],
        "reason": signal["reason"],
        "raw_value": signal["raw_value"],
    } == {
        "status": "available",
        "direction": "neutral",
        "signal": "neutral",
        "state": "neutral",
        "strength": 0.0,
        "reason": "Position Bollinger courante: neutral",
        "raw_value": 15.0,
    }
    assert signal["state"] == detect_bollinger_signal(close, bands)
    assert {
        "middle_band",
        "upper_band",
        "lower_band",
        "band_width",
        "band_width_percent",
        "band_position",
    } <= set(signal["components"] or {})


def test_bollinger_width_constant_series_has_deterministic_center_position() -> None:
    close = series([5, 5, 5])
    derived = calculate_bollinger_band_width(close, calculate_bollinger_bands(close, period=3))
    assert derived["band_width"].iloc[-1] == 0
    assert derived["band_width_percent"].iloc[-1] == 0
    assert derived["band_position"].iloc[-1] == 0.5


def test_donchian_descriptive_previous_width_position_and_strict_breakout() -> None:
    high = series([10, 11, 14])
    low = series([8, 9, 10])
    close = series([9, 10, 13])
    data = calculate_donchian_channels(high, low, close, period=2)
    assert data["upper_channel"].iloc[-1] == 14
    assert data["lower_channel"].iloc[-1] == 9
    assert data["middle_channel"].iloc[-1] == 11.5
    assert data["previous_upper_channel"].iloc[-1] == 11
    assert data["previous_lower_channel"].iloc[-1] == 8
    assert data["channel_width"].iloc[-1] == 5
    assert data["channel_width_percent"].iloc[-1] == pytest.approx(100 * 5 / 11.5)
    assert data["channel_position"].iloc[-1] == pytest.approx(0.8)
    signal = build_donchian_signal(data, close)
    assert (signal["signal"], signal["state"], signal["direction"]) == (
        "breakout_up",
        "above_channel",
        "bullish",
    )

    equal_close = close.copy()
    equal_close.iloc[-1] = 11
    equal_signal = build_donchian_signal(
        calculate_donchian_channels(high, low, equal_close, 2), equal_close
    )
    assert equal_signal["signal"] is None
    assert equal_signal["state"] == "inside_channel"


def test_donchian_down_breakout_warmup_constant_and_validation() -> None:
    high = series([12, 11, 10])
    low = series([10, 9, 6])
    close = series([11, 10, 7])
    data = calculate_donchian_channels(high, low, close, 2)
    signal = build_donchian_signal(data, close)
    assert signal["signal"] == "breakout_down"
    assert signal["direction"] == "bearish"
    assert (
        build_donchian_signal(
            calculate_donchian_channels(high.iloc[:2], low.iloc[:2], close.iloc[:2], 2),
            close.iloc[:2],
        )["status"]
        == "insufficient_data"
    )

    flat = series([10, 10, 10])
    flat_signal = build_donchian_signal(calculate_donchian_channels(flat, flat, flat, 2), flat)
    assert flat_signal["status"] == "available"

    flat_components = flat_signal.get("components")
    assert flat_components is not None
    assert flat_components["channel_position"]["value"] == 0.5
    with pytest.raises(ValueError):
        calculate_donchian_channels(high, low, close, 0)
    invalid = calculate_donchian_channels(series([12, 11, 8]), series([10, 9, 9]), close, 2)
    assert build_donchian_signal(invalid, close)["status"] == "invalid_data"


def test_donchian_signal_exposes_continuous_normalized_components() -> None:
    high = series(
        [
            10.0,
            11.0,
            14.0,
        ]
    )
    low = series(
        [
            8.0,
            9.0,
            10.0,
        ]
    )
    close = series(
        [
            9.0,
            10.0,
            13.0,
        ]
    )

    signal = build_donchian_signal(
        calculate_donchian_channels(
            high,
            low,
            close,
            period=2,
        ),
        close,
    )
    components = signal.get("components")

    current_width_percent = 100.0 * 5.0 / 11.5
    previous_width_percent = 100.0 * 3.0 / 9.5

    assert signal["status"] == "available"
    assert signal["signal"] == "breakout_up"
    assert signal["direction"] == "bullish"
    assert signal["state"] == "above_channel"
    assert components is not None

    assert components["upper_channel"]["value"] == pytest.approx(14.0)
    assert components["upper_channel"]["normalized_value"] == pytest.approx(14 / 13)

    assert components["middle_channel"]["value"] == pytest.approx(11.5)
    assert components["lower_channel"]["value"] == pytest.approx(9.0)

    assert components["previous_upper_channel"]["value"] == pytest.approx(11.0)
    assert components["previous_middle_channel"]["value"] == pytest.approx(9.5)
    assert components["previous_lower_channel"]["value"] == pytest.approx(8.0)

    assert components["channel_width"]["value"] == pytest.approx(5.0)
    assert components["channel_width"]["normalized_value"] == pytest.approx(5 / 13)
    assert components["channel_width_percent"]["value"] == pytest.approx(current_width_percent)
    assert components["channel_position"]["value"] == pytest.approx(0.8)

    assert components["previous_channel_width"]["value"] == pytest.approx(3.0)
    assert components["previous_channel_width_percent"]["value"] == pytest.approx(
        previous_width_percent
    )
    assert components["previous_channel_position"]["value"] == pytest.approx(2 / 3)

    assert components["price_to_upper_distance"]["value"] == pytest.approx(-1.0)
    assert components["price_to_upper_distance"]["normalized_value"] == pytest.approx(-1 / 13)

    assert components["price_to_middle_distance"]["value"] == pytest.approx(1.5)
    assert components["price_to_lower_distance"]["value"] == pytest.approx(4.0)
    assert components["price_to_previous_upper_distance"]["value"] == pytest.approx(2.0)
    assert components["price_to_previous_lower_distance"]["value"] == pytest.approx(5.0)

    assert components["upper_channel_change"]["value"] == pytest.approx(3.0)
    assert components["upper_channel_change"]["normalized_value"] == pytest.approx(3 / 25)

    assert components["middle_channel_change"]["value"] == pytest.approx(2.0)
    assert components["middle_channel_change"]["normalized_value"] == pytest.approx(2 / 21)

    assert components["lower_channel_change"]["value"] == pytest.approx(1.0)
    assert components["lower_channel_change"]["normalized_value"] == pytest.approx(1 / 17)

    assert components["channel_width_percent_change"]["value"] == pytest.approx(
        current_width_percent - previous_width_percent
    )
    assert components["channel_width_percent_change"]["normalized_value"] == pytest.approx(
        (current_width_percent - previous_width_percent) / 100.0
    )

    assert components["channel_position_change"]["value"] == pytest.approx(0.8 - (2 / 3))


def test_keltner_reuses_ema_atr_and_calculates_components() -> None:
    close = series([10, 11, 12, 13, 14])
    high, low = close + 1, close - 1
    ema = calculate_ema(close, 3)
    atr = calculate_atr(high, low, close, 2)["atr"]
    data = calculate_keltner_channels(
        high,
        low,
        close,
        ema_period=3,
        atr_period=2,
        multiplier=2,
        atr=atr,
        middle_line=ema,
    )
    pd.testing.assert_series_equal(data["middle_line"], ema)
    pd.testing.assert_series_equal(data["atr"], atr)
    assert data["upper_channel"].iloc[-1] == pytest.approx(ema.iloc[-1] + 2 * atr.iloc[-1])
    assert data["lower_channel"].iloc[-1] == pytest.approx(ema.iloc[-1] - 2 * atr.iloc[-1])
    assert data["channel_width"].iloc[-1] == pytest.approx(4 * atr.iloc[-1])


def test_keltner_breakout_is_causal_and_not_repeated() -> None:
    close = series([10, 12])
    data = {
        "middle_line": series([10, 10]),
        "upper_channel": series([11, 11]),
        "lower_channel": series([9, 9]),
        "atr": series([1, 1]),
        "channel_width": series([2, 2]),
        "channel_width_percent": series([20, 20]),
        "channel_position": series([0.5, 1.5]),
    }
    first = build_keltner_signal(data, close)
    assert first["signal"] == "breakout_up"
    assert first["direction"] == "bullish"

    repeated_close = series([12, 13])
    repeated = build_keltner_signal(data, repeated_close)
    assert repeated["signal"] is None
    assert repeated["state"] == "above_channel"
    with pytest.raises(ValueError):
        calculate_keltner_channels(close, close, close, multiplier=0)
    invalid = calculate_keltner_channels(
        series([11, 8]), series([9, 9]), close, ema_period=1, atr_period=1
    )
    assert build_keltner_signal(invalid, close)["status"] == "invalid_data"


def test_keltner_signal_exposes_continuous_normalized_components() -> None:
    close = series(
        [
            10.0,
            12.0,
        ]
    )
    data = {
        "middle_line": series(
            [
                10.0,
                10.5,
            ]
        ),
        "upper_channel": series(
            [
                11.0,
                11.5,
            ]
        ),
        "lower_channel": series(
            [
                9.0,
                9.5,
            ]
        ),
        "atr": series(
            [
                1.0,
                1.0,
            ]
        ),
        "channel_width": series(
            [
                2.0,
                2.0,
            ]
        ),
        "channel_width_percent": series(
            [
                20.0,
                100.0 * 2.0 / 10.5,
            ]
        ),
        "channel_position": series(
            [
                0.5,
                1.25,
            ]
        ),
        "_invalid_ohlc": series(
            [
                0.0,
                0.0,
            ]
        ),
    }

    signal = build_keltner_signal(
        data,
        close,
    )
    components = signal.get("components")

    assert signal["status"] == "available"
    assert signal["signal"] == "breakout_up"
    assert signal["direction"] == "bullish"
    assert signal["state"] == "above_channel"
    assert signal["strength"] == pytest.approx(1.0)
    assert components is not None

    assert components["middle_line"]["value"] == pytest.approx(10.5)
    assert components["middle_line"]["normalized_value"] == pytest.approx(10.5 / 12)

    assert components["upper_channel"]["value"] == pytest.approx(11.5)
    assert components["lower_channel"]["value"] == pytest.approx(9.5)

    assert components["atr"]["value"] == pytest.approx(1.0)
    assert components["atr"]["normalized_value"] == pytest.approx(1 / 12)

    assert components["channel_width"]["value"] == pytest.approx(2.0)
    assert components["channel_width"]["normalized_value"] == pytest.approx(2 / 12)

    assert components["channel_width_percent"]["normalized_value"] == pytest.approx(2 / 10.5)
    assert components["channel_position"]["value"] == pytest.approx(1.25)

    assert components["price_to_middle_distance"]["value"] == pytest.approx(1.5)
    assert components["price_to_upper_distance"]["value"] == pytest.approx(0.5)
    assert components["price_to_lower_distance"]["value"] == pytest.approx(2.5)

    assert components["price_to_previous_upper_distance"]["value"] == pytest.approx(1.0)
    assert components["price_to_previous_lower_distance"]["value"] == pytest.approx(3.0)

    assert components["price_to_middle_atr"]["value"] == pytest.approx(1.5)
    assert components["price_to_previous_upper_atr"]["value"] == pytest.approx(1.0)

    assert components["previous_middle_line"]["value"] == pytest.approx(10.0)
    assert components["previous_upper_channel"]["value"] == pytest.approx(11.0)
    assert components["previous_lower_channel"]["value"] == pytest.approx(9.0)
    assert components["previous_channel_position"]["value"] == pytest.approx(0.5)

    assert components["middle_line_change"]["value"] == pytest.approx(0.5)
    assert components["middle_line_change"]["normalized_value"] == pytest.approx(0.5 / 20.5)

    assert components["upper_channel_change"]["value"] == pytest.approx(0.5)
    assert components["lower_channel_change"]["value"] == pytest.approx(0.5)
    assert components["atr_change"]["value"] == pytest.approx(0.0)
    assert components["channel_width_change"]["value"] == pytest.approx(0.0)

    assert components["channel_width_percent_change"]["value"] == pytest.approx(
        (100.0 * 2.0 / 10.5) - 20.0
    )
    assert components["channel_position_change"]["value"] == pytest.approx(0.75)


def test_keltner_components_accept_missing_previous_values() -> None:
    signal = build_keltner_signal(
        {
            "middle_line": series([10.0]),
            "upper_channel": series([11.0]),
            "lower_channel": series([9.0]),
            "atr": series([1.0]),
            "channel_width": series([2.0]),
            "channel_width_percent": series([20.0]),
            "channel_position": series([0.5]),
            "_invalid_ohlc": series([0.0]),
        },
        series([10.0]),
    )

    components = signal.get("components")

    assert signal["status"] == "available"
    assert signal["signal"] is None
    assert components is not None

    assert components["previous_middle_line"]["value"] is None
    assert components["previous_upper_channel"]["value"] is None
    assert components["previous_lower_channel"]["value"] is None
    assert components["previous_atr"]["value"] is None
    assert components["previous_channel_width"]["value"] is None
    assert components["previous_channel_width_percent"]["value"] is None
    assert components["previous_channel_position"]["value"] is None

    assert components["middle_line_change"]["value"] is None
    assert components["upper_channel_change"]["value"] is None
    assert components["lower_channel_change"]["value"] is None
    assert components["atr_change"]["value"] is None
    assert components["channel_width_change"]["value"] is None
    assert components["channel_width_percent_change"]["value"] is None
    assert components["channel_position_change"]["value"] is None

    assert components["price_to_previous_upper_distance"]["value"] is None
    assert components["price_to_previous_lower_distance"]["value"] is None


def test_phase_8_3_calculations_ignore_future_candles() -> None:
    close = series([10, 11, 12, 13, 14, 15])
    high, low = close + 1, close - 1
    mutated_close = pd.concat([close, series([1000])], ignore_index=True)
    mutated_high = pd.concat([high, series([1200])], ignore_index=True)
    mutated_low = pd.concat([low, series([900])], ignore_index=True)

    original_bands = calculate_bollinger_bands(close, 3)
    future_bands = calculate_bollinger_bands(mutated_close, 3)
    for name, values in calculate_bollinger_band_width(close, original_bands).items():
        pd.testing.assert_series_equal(
            values.reset_index(drop=True),
            calculate_bollinger_band_width(mutated_close, future_bands)[name]
            .iloc[:-1]
            .reset_index(drop=True),
        )
    for calculator, kwargs in (
        (calculate_donchian_channels, {"period": 3}),
        (
            calculate_keltner_channels,
            {"ema_period": 3, "atr_period": 2, "multiplier": 2},
        ),
    ):
        original = calculator(high, low, close, **kwargs)
        future = calculator(mutated_high, mutated_low, mutated_close, **kwargs)
        for name in original:
            pd.testing.assert_series_equal(
                original[name].reset_index(drop=True),
                future[name].iloc[:-1].reset_index(drop=True),
            )


def test_phase_8_3_live_replay_parity_and_business_neutrality() -> None:
    rows = candles()[30:91]
    decision = rows[-1].close_time
    assert decision is not None
    base_config = ScanConfig(
        timeframe="1m",
        min_ohlcv_bars=60,
        use_rsi=False,
        use_ma=False,
        ma_timeframes=[],
        min_trend_score=0,
        use_macd=False,
        use_bollinger=True,
        bollinger_period=20,
        use_stochastic=False,
        use_confluence_score=False,
    )
    observed_config = ScanConfig.model_validate(
        {
            **base_config.model_dump(
                exclude={
                    "donchian",
                    "keltner",
                }
            ),
            "donchian": {
                "version": 1,
                "enabled": True,
                "period": 20,
            },
            "keltner": {
                "version": 1,
                "enabled": True,
                "ema_period": 20,
                "atr_period": 10,
                "multiplier": 2,
            },
        }
    )
    base = evaluate_information_set(
        job_id="base",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=rows,
        trend_candles={},
        config=base_config,
    ).model_copy(update={"id": 1})
    observed = evaluate_information_set(
        job_id="observed",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=rows,
        trend_candles={},
        config=observed_config,
    ).model_copy(update={"id": 1})
    assert {"bollinger", "donchian", "keltner"} <= set(observed.indicator_signals)
    json.dumps(observed.model_dump(mode="json"), allow_nan=False)
    for field in (
        "accepted",
        "rejection_stage",
        "rejection_reason",
        "confluence_score",
        "confluence_grade",
        "confluence_factors",
        "filter_trace",
    ):
        assert getattr(observed, field) == getattr(base, field)
    assert observed.indicator_signals["bollinger"].model_dump(
        exclude={"components"}
    ) == base.indicator_signals["bollinger"].model_dump(exclude={"components"})
    backtest_config = BacktestConfig(
        symbols=["SYN/USDC"],
        start=datetime.fromtimestamp(rows[0].open_time / 1000, tz=timezone.utc),
        end=datetime.fromtimestamp(decision / 1000, tz=timezone.utc),
        signal_config=base_config,
    )
    observed_backtest_config = backtest_config.model_copy(update={"signal_config": observed_config})
    assert calculate_forward_outcomes(1, rows, len(rows) - 2, backtest_config) == (
        calculate_forward_outcomes(1, rows, len(rows) - 2, observed_backtest_config)
    )

    ohlcv = [[row.open_time, row.open, row.high, row.low, row.close, row.volume] for row in rows]
    frame, bundle = calculate_indicator_bundle(
        ohlcv, MarketIndicatorConfig.from_scan(observed_config)
    )
    market = calculate_market_snapshot(
        frame, bundle, MarketIndicatorConfig.from_scan(observed_config)
    )
    assert market["indicator_signals"] == {
        name: signal.model_dump(mode="python")
        for name, signal in observed.indicator_signals.items()
    }

    simulation_config = PortfolioSimulationConfig(
        quote_asset="USDC",
        initial_capital=Decimal("1000"),
        fee_rate=Decimal("0"),
    )
    base_portfolio = simulate_portfolio(
        symbol="SYN/USDC",
        steps=build_portfolio_simulation_steps(
            observations=[base],
            primary_candles=rows,
            symbol="SYN/USDC",
            timeframe="1m",
        ),
        config=simulation_config,
    )
    observed_portfolio = simulate_portfolio(
        symbol="SYN/USDC",
        steps=build_portfolio_simulation_steps(
            observations=[observed],
            primary_candles=rows,
            symbol="SYN/USDC",
            timeframe="1m",
        ),
        config=simulation_config,
    )
    assert observed.accepted == base.accepted
    assert observed_portfolio.orders == base_portfolio.orders
    assert observed_portfolio.executions == base_portfolio.executions
    assert observed_portfolio.trades == base_portfolio.trades
    assert observed_portfolio.equity_curve == base_portfolio.equity_curve
    assert observed_portfolio.final_cash == base_portfolio.final_cash
    assert observed_portfolio.final_equity == base_portfolio.final_equity
    assert observed_portfolio.metrics == base_portfolio.metrics


def test_phase_8_3_config_defaults_validation_and_mutualization() -> None:
    legacy = ScanConfig()
    assert legacy.donchian is None
    assert legacy.keltner is None
    with pytest.raises(ValueError):
        ScanConfig.model_validate({"donchian": {"version": 1, "period": 0}})

    with pytest.raises(ValueError):
        ScanConfig.model_validate({"keltner": {"version": 1, "multiplier": math.inf}})

    prices = series([100 + index for index in range(50)])
    data, signals = calculate_extended_indicator_bundle(
        high=prices + 1,
        low=prices - 1,
        close=prices,
        use_atr=True,
        atr_period=10,
        use_keltner=True,
        keltner_atr_period=10,
        use_donchian=True,
    )
    assert set(signals) == {"atr", "donchian", "keltner"}
    assert data["atr"]["atr"].equals(data["keltner"]["atr"])


def test_phase_8_3_openapi_and_historical_payload_compatibility() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    properties = schema["components"]["schemas"]["ScanConfig"]["properties"]
    assert {"donchian", "keltner"} <= set(properties)
    historical = ScanConfig().model_dump(
        mode="json", exclude={"atr", "adx", "supertrend", "donchian", "keltner"}
    )
    reparsed = ScanConfig.model_validate(historical)
    assert reparsed.donchian is None
    assert reparsed.keltner is None
    with pytest.raises(ValueError):
        ScanConfig.model_validate(
            {
                "donchian": {
                    "version": 1,
                    "enabled": True,
                    "period": 20,
                    "unknown": 1,
                }
            }
        )

    with pytest.raises(ValueError):
        ScanConfig.model_validate(
            {
                "keltner": {
                    "version": 1,
                    "enabled": True,
                    "ema_period": 20,
                    "atr_period": 10,
                    "multiplier": 2,
                    "unknown": 1,
                }
            }
        )
