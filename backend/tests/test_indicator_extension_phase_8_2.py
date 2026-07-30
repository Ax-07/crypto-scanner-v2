from __future__ import annotations

import math
import json
import time
from decimal import Decimal

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.settings import MarketIndicatorConfig, ScanConfig
from app.domain.backtesting import evaluate_information_set
from app.domain.indicator_bundle import calculate_extended_indicator_bundle
from app.domain.indicators import (
    build_adx_signal,
    build_atr_signal,
    build_supertrend_signal,
    calculate_adx_dmi,
    calculate_atr,
    calculate_directional_movement,
    calculate_natr,
    calculate_supertrend,
    calculate_true_range,
)
from app.domain.portfolio import PortfolioSimulationConfig, simulate_portfolio
from app.main import app
from app.models.scanner import IndicatorSignalModel
from app.services.market_stream import calculate_indicator_bundle, calculate_market_snapshot
from app.services.portfolio_replay import build_portfolio_simulation_steps
from tests.fixtures.synthetic_backtest_v1 import candles


def series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def test_true_range_atr_and_natr_follow_wilder_seed() -> None:
    high = series([10, 12, 13])
    low = series([8, 9, 11])
    close = series([9, 11, 12])

    true_range = calculate_true_range(high, low, close)
    assert true_range.tolist() == pytest.approx([2, 3, 2])
    atr = calculate_atr(high, low, close, period=2, true_range=true_range)["atr"]
    assert math.isnan(atr.iloc[0])
    assert atr.iloc[1:].tolist() == pytest.approx([2.5, 2.25])
    assert calculate_natr(atr, close).iloc[-1] == pytest.approx(18.75)


def test_directional_movement_ties_are_zero_and_adx_availability_is_exact() -> None:
    high = series([10, 11, 12])
    low = series([8, 7, 8])
    close = series([9, 10, 11])
    movement = calculate_directional_movement(high, low)
    assert movement["plus_dm"].tolist() == pytest.approx([0, 0, 1])
    assert movement["minus_dm"].tolist() == pytest.approx([0, 0, 0])

    data = calculate_adx_dmi(series([10, 12, 13]), series([8, 9, 11]), close, period=2)
    assert data["plus_di"].iloc[1] == pytest.approx(40)
    assert data["adx"].first_valid_index() == 2
    assert data["adx"].iloc[2] == pytest.approx(100)
    assert build_adx_signal(data)["status"] == "available"


def test_zero_denominators_are_defined_and_invalid_ohlc_is_explicit() -> None:
    flat = series([10, 10, 10, 10])
    data = calculate_adx_dmi(flat, flat, flat, period=2)
    assert data["plus_di"].dropna().eq(0).all()
    assert data["minus_di"].dropna().eq(0).all()
    assert data["dx"].dropna().eq(0).all()
    assert data["adx"].dropna().eq(0).all()

    invalid_high = series([10, 10, 8])
    invalid_low = series([8, 9, 9])
    invalid_close = series([9, 9.5, 8.5])
    invalid_adx = calculate_adx_dmi(invalid_high, invalid_low, invalid_close, period=2)
    assert build_adx_signal(invalid_adx)["status"] == "invalid_data"
    invalid_atr = calculate_atr(invalid_high, invalid_low, invalid_close, period=2)
    assert build_atr_signal(invalid_atr, invalid_close)["status"] == "invalid_data"


def test_atr_is_neutral_and_events_only_describe_state_transitions() -> None:
    close = series([10, 10, 10, 10, 10])
    data = {
        "true_range": series([1, 1, 1, 1, 1]),
        "atr": series([math.nan, 1, 1, 1, 1]),
        "natr": series([math.nan, 10, 10, 11, 12]),
    }
    signal = build_atr_signal(data, close)
    assert signal["direction"] == "neutral"
    assert signal["state"] == "expanding"
    assert signal["signal"] is None
    data["natr"].iloc[-1] = 10
    signal = build_atr_signal(data, close)
    assert signal["state"] == "contracting"
    assert signal["signal"] == "volatility_contraction"


def test_supertrend_is_causal_and_flips_only_on_regime_changes() -> None:
    high = series([11, 12, 13, 12, 9, 8, 11])
    low = series([9, 10, 11, 9, 6, 5, 8])
    close = series([10, 11, 12, 10, 7, 6, 10])
    full = calculate_supertrend(high, low, close, atr_period=2, multiplier=1)
    prefix = calculate_supertrend(high.iloc[:-1], low.iloc[:-1], close.iloc[:-1], 2, 1)
    for name in ("supertrend", "upper_band", "lower_band", "atr", "trend"):
        pd.testing.assert_series_equal(
            full[name].iloc[:-1].reset_index(drop=True),
            prefix[name].reset_index(drop=True),
            check_names=False,
        )
    signal = build_supertrend_signal(full, close)
    previous_direction = full["trend"].dropna().iloc[-2]
    assert signal["signal"] is (
        None
        if previous_direction == full["trend"].dropna().iloc[-1]
        else ("bullish_flip" if signal["direction"] == "bullish" else "bearish_flip")
    )


def test_bundle_mutualizes_inputs_and_keeps_disabled_extensions_absent() -> None:
    prices = series([100 + index for index in range(40)])
    empty_data, empty_signals = calculate_extended_indicator_bundle(
        high=prices + 1,
        low=prices - 1,
        close=prices,
    )
    assert empty_data == {}
    assert empty_signals == {}

    data, signals = calculate_extended_indicator_bundle(
        high=prices + 1,
        low=prices - 1,
        close=prices,
        use_atr=True,
        atr_period=10,
        use_adx=True,
        adx_period=10,
        use_supertrend=True,
        supertrend_atr_period=10,
    )
    assert set(signals) == {"atr", "adx", "supertrend"}
    assert data["atr"]["atr"].equals(data["supertrend"]["atr"])
    assert data["atr"]["true_range"].equals(data["adx"]["true_range"])


def test_extensions_are_observable_but_business_neutral() -> None:
    rows = candles()
    primary = rows[30:90]
    decision = primary[-1].close_time
    assert decision is not None
    legacy = ScanConfig(
        timeframe="1m",
        min_ohlcv_bars=60,
        use_rsi=False,
        use_ma=False,
        ma_timeframes=[],
        min_trend_score=0,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=False,
        use_confluence_score=False,
    )
    extended = ScanConfig(
        **legacy.model_dump(exclude={"atr", "adx", "supertrend"}),
        atr={"version": 1, "enabled": True, "period": 14},
        adx={
            "version": 1,
            "enabled": True,
            "period": 14,
            "weak_threshold": 20,
            "strong_threshold": 25,
        },
        supertrend={
            "version": 1,
            "enabled": True,
            "atr_period": 10,
            "multiplier": 3,
        },
    )
    base = evaluate_information_set(
        job_id="base",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=primary,
        trend_candles={},
        config=legacy,
    )
    observed = evaluate_information_set(
        job_id="extended",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=primary,
        trend_candles={},
        config=extended,
    )
    base = base.model_copy(update={"id": 1})
    observed = observed.model_copy(update={"id": 1})
    assert set(observed.indicator_signals) == {"atr", "adx", "supertrend"}
    public_payload = observed.model_dump(mode="json")
    assert "natr" in public_payload["indicator_signals"]["atr"]["components"]
    json.dumps(public_payload, allow_nan=False)
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

    # Nouveaux indicateurs activés -> accepted, trades et equity inchangés.
    simulation_config = PortfolioSimulationConfig(
        quote_asset="USDC",
        initial_capital=Decimal("1000"),
        fee_rate=Decimal("0"),
    )
    replay_candles = rows[30:91]
    base_result = simulate_portfolio(
        symbol="SYN/USDC",
        steps=build_portfolio_simulation_steps(
            observations=[base],
            primary_candles=replay_candles,
            symbol="SYN/USDC",
            timeframe="1m",
        ),
        config=simulation_config,
    )
    observed_result = simulate_portfolio(
        symbol="SYN/USDC",
        steps=build_portfolio_simulation_steps(
            observations=[observed],
            primary_candles=replay_candles,
            symbol="SYN/USDC",
            timeframe="1m",
        ),
        config=simulation_config,
    )
    assert observed.accepted == base.accepted
    assert observed_result.trades == base_result.trades
    assert observed_result.equity_curve == base_result.equity_curve


def test_market_and_backtest_use_identical_extension_signals() -> None:
    rows = candles()[30:91]
    config = ScanConfig(
        timeframe="1m",
        min_ohlcv_bars=60,
        use_rsi=False,
        use_ma=False,
        ma_timeframes=[],
        min_trend_score=0,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=False,
        use_confluence_score=False,
        atr={"version": 1, "enabled": True, "period": 14},
        adx={
            "version": 1,
            "enabled": True,
            "period": 14,
            "weak_threshold": 20,
            "strong_threshold": 25,
        },
        supertrend={"version": 1, "enabled": True, "atr_period": 10, "multiplier": 3},
    )
    decision = rows[-1].close_time
    assert decision is not None
    backtest = evaluate_information_set(
        job_id="parity",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=rows,
        trend_candles={},
        config=config,
    )
    ohlcv = [[row.open_time, row.open, row.high, row.low, row.close, row.volume] for row in rows]
    profile = MarketIndicatorConfig.from_scan(config)
    frame, bundle = calculate_indicator_bundle(ohlcv, profile)
    market = calculate_market_snapshot(frame, bundle, profile)
    assert market["indicator_signals"] == {
        name: signal.model_dump(mode="python")
        for name, signal in backtest.indicator_signals.items()
    }


def test_extension_bundle_records_a_non_fragile_timing() -> None:
    prices = series([100 + index * 0.1 for index in range(500)])
    started = time.perf_counter()
    _, signals = calculate_extended_indicator_bundle(
        high=prices + 1,
        low=prices - 1,
        close=prices,
        use_atr=True,
        use_adx=True,
        use_supertrend=True,
    )
    elapsed_seconds = time.perf_counter() - started
    assert elapsed_seconds >= 0
    assert set(signals) == {"atr", "adx", "supertrend"}


def test_config_and_openapi_expose_versioned_optional_blocks_and_components() -> None:
    legacy = ScanConfig()
    assert legacy.atr is legacy.adx is legacy.supertrend is None
    with pytest.raises(ValueError):
        ScanConfig(adx={"version": 1, "weak_threshold": 25, "strong_threshold": 20})

    schema = TestClient(app).get("/openapi.json").json()
    scan_properties = schema["components"]["schemas"]["ScanConfig"]["properties"]
    assert {"atr", "adx", "supertrend"} <= set(scan_properties)
    signal_schema = IndicatorSignalModel.model_json_schema()
    component_reference = signal_schema["properties"]["components"]["anyOf"][0]
    component_name = component_reference["additionalProperties"]["$ref"].split("/")[-1]
    component_properties = signal_schema["$defs"][component_name]["properties"]
    assert {"value", "normalized_value", "unit"} == set(component_properties)
