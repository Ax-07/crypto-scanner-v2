from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from inspect import signature

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.domain.candles import Candle
from app.domain.portfolio import PortfolioSimulationConfig, simulate_portfolio
from app.models.backtest import BacktestConfig, SignalObservation
from app.models.portfolio import PortfolioSimulationConfigV1
from app.services.portfolio_replay import (
    PortfolioReplayError,
    backtest_config_fingerprint,
    build_portfolio_simulation_steps,
    to_internal_portfolio_config,
    to_public_portfolio_result,
    to_public_portfolio_summary,
)
from app.api.backtests import router
from tests.test_backtesting_domain import signal_config

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def public_config(**updates: object) -> PortfolioSimulationConfigV1:
    values: dict[str, object] = {"quote_asset": "USDC"}
    values.update(updates)
    return PortfolioSimulationConfigV1.model_validate(values)


def backtest_config(portfolio: dict[str, object] | None = None, **updates) -> BacktestConfig:
    values = {
        "symbols": ["BTC/USDC"],
        "start": START,
        "end": START + timedelta(hours=4),
        "signal_config": signal_config(),
        "portfolio_simulation": portfolio,
    }
    values.update(updates)
    return BacktestConfig.model_validate(values)


def candle(index: int, *, open_price: float = 100, close_price: float = 101) -> Candle:
    opened = int((START + timedelta(minutes=index)).timestamp() * 1_000)
    return Candle(
        exchange_id="binance",
        market_type="spot",
        symbol="BTC/USDC",
        timeframe="1m",
        open_time=opened,
        open=open_price,
        high=max(open_price, close_price),
        low=min(open_price, close_price),
        close=close_price,
        volume=1,
        close_time=opened + 60_000,
    )


def observation(index: int, *, accepted: bool = False) -> SignalObservation:
    return SignalObservation(
        id=index + 1,
        job_id="portfolio-adapter",
        symbol="BTC/USDC",
        timeframe="1m",
        source_open_time=START + timedelta(minutes=index),
        decision_time=START + timedelta(minutes=index + 1),
        accepted=accepted,
        close=101,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_capital", "0"),
        ("initial_capital", "-1"),
        ("initial_capital", "NaN"),
        ("initial_capital", "Infinity"),
        ("fee_rate", "-0.1"),
        ("fee_rate", "1"),
        ("slippage_rate", "-0.1"),
        ("slippage_rate", "1"),
    ],
)
def test_public_portfolio_config_rejects_invalid_decimals(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        public_config(**{field: value})


@pytest.mark.parametrize(
    "payload",
    [
        {"quote_asset": "", "position_sizing": {"value": "100"}},
        {"quote_asset": "USDC", "version": 2},
        {"quote_asset": "USDC", "unknown": True},
        {"quote_asset": "USDC", "execution_policy": "signal_close"},
        {"quote_asset": "USDC", "end_of_test_policy": "mark_to_market"},
        {"quote_asset": "USDC", "position_sizing": {"mode": "fixed", "value": "10"}},
        {"quote_asset": "USDC", "position_sizing": {"value": "0"}},
        {"quote_asset": "USDC", "position_sizing": {"value": "100.01"}},
        {"quote_asset": "USDC", "position_sizing": {"value": "50", "unknown": 1}},
    ],
)
def test_public_portfolio_config_is_strict(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PortfolioSimulationConfigV1.model_validate(payload)


def test_public_portfolio_config_defaults_and_decimal_serialization() -> None:
    config = public_config(initial_capital="10000.00", fee_rate="0.0010")
    assert config.quote_asset == "USDC"
    assert config.position_sizing.value == Decimal("100")
    assert config.model_dump(mode="json") == {
        "version": 1,
        "quote_asset": "USDC",
        "initial_capital": "10000",
        "position_sizing": {"mode": "percent_cash", "value": "100"},
        "execution_policy": "next_open",
        "fee_rate": "0.001",
        "slippage_rate": "0",
        "end_of_test_policy": "force_close",
    }


def test_backtest_config_validates_symbol_quote_and_replay_mode() -> None:
    assert backtest_config({"quote_asset": "usdc"}).portfolio_simulation is not None
    with pytest.raises(ValidationError, match="quote_asset"):
        backtest_config({"quote_asset": "EUR"})
    with pytest.raises(ValidationError, match="exactement un symbole"):
        backtest_config({"quote_asset": "USDC"}, symbols=["BTC/USDC", "ETH/USDC"])
    with pytest.raises(ValidationError, match="every_bar"):
        backtest_config({"quote_asset": "USDC"}, replay_mode="state_changes")
    non_standard = backtest_config(
        {"quote_asset": "USDC"},
        symbols=["BTCUSDC"],
    )
    assert non_standard.portfolio_simulation is not None


def test_public_to_internal_adapter_preserves_values() -> None:
    public = public_config(
        initial_capital="1234.50",
        position_sizing={"mode": "percent_cash", "value": "50.25"},
        fee_rate="0.0025",
        slippage_rate="0.0005",
    )
    internal = to_internal_portfolio_config(public)
    assert internal == PortfolioSimulationConfig(
        quote_asset="USDC",
        initial_capital=Decimal("1234.50"),
        position_size_percent=Decimal("50.25"),
        fee_rate=Decimal("0.0025"),
        slippage_rate=Decimal("0.0005"),
    )


def test_step_adapter_maps_exact_candles_and_preserves_order() -> None:
    observations = [observation(0, accepted=True), observation(1), observation(2, accepted=True)]
    steps = build_portfolio_simulation_steps(
        observations=observations,
        primary_candles=[candle(0), candle(1, open_price=102), candle(2)],
        symbol="BTC/USDC",
        timeframe="1m",
    )
    assert [item.observation_id for item in steps] == ["1", "2", "3"]
    assert [item.accepted for item in steps] == [True, False, True]
    assert steps[1].open_price == Decimal("102")


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda observations, candles: observations.__setitem__(
                1, observations[1].model_copy(update={"id": 1})
            ),
            "portfolio_duplicate_observation",
        ),
        (
            lambda observations, candles: observations.__setitem__(
                1,
                observations[1].model_copy(
                    update={"source_open_time": START + timedelta(minutes=3)}
                ),
            ),
            "portfolio_missing_primary_candle",
        ),
        (
            lambda observations, candles: observations.__setitem__(
                1,
                observations[1].model_copy(update={"decision_time": START + timedelta(minutes=3)}),
            ),
            "portfolio_incoherent_decision_time",
        ),
        (
            lambda observations, candles: candles.append(candles[0]),
            "portfolio_duplicate_primary_candle",
        ),
        (
            lambda observations, candles: observations.__setitem__(
                1,
                observations[1].model_copy(
                    update={
                        "source_open_time": START + timedelta(minutes=2),
                        "decision_time": START + timedelta(minutes=3),
                    }
                ),
            ),
            "portfolio_time_gap",
        ),
        (
            lambda observations, candles: candles.__setitem__(1, candle(1, open_price=0)),
            "portfolio_invalid_price",
        ),
    ],
)
def test_step_adapter_rejects_incoherent_inputs(mutate, code: str) -> None:
    observations = [observation(0), observation(1)]
    candles = [candle(0), candle(1)]
    if code == "portfolio_time_gap":
        candles[1] = candle(2)
    mutate(observations, candles)
    with pytest.raises(PortfolioReplayError) as raised:
        build_portfolio_simulation_steps(
            observations=observations,
            primary_candles=candles,
            symbol="BTC/USDC",
            timeframe="1m",
        )
    assert raised.value.code == code


def test_step_adapter_rejects_naive_timestamp_and_symbol_mismatch() -> None:
    naive = observation(0).model_copy(update={"source_open_time": START.replace(tzinfo=None)})
    with pytest.raises(PortfolioReplayError, match="portfolio_invalid_timestamp"):
        build_portfolio_simulation_steps(
            observations=[naive],
            primary_candles=[candle(0)],
            symbol="BTC/USDC",
            timeframe="1m",
        )
    wrong_symbol = observation(0).model_copy(update={"symbol": "ETH/USDC"})
    with pytest.raises(PortfolioReplayError, match="portfolio_symbol_mismatch"):
        build_portfolio_simulation_steps(
            observations=[wrong_symbol],
            primary_candles=[candle(0)],
            symbol="BTC/USDC",
            timeframe="1m",
        )


def test_public_summary_is_a_direct_serializable_projection() -> None:
    steps = build_portfolio_simulation_steps(
        observations=[observation(0, accepted=True), observation(1, accepted=False)],
        primary_candles=[candle(0), candle(1, open_price=100, close_price=110)],
        symbol="BTC/USDC",
        timeframe="1m",
    )
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=steps,
        config=PortfolioSimulationConfig(
            quote_asset="USDC",
            initial_capital=Decimal("1000"),
            fee_rate=Decimal("0"),
        ),
    )
    summary = to_public_portfolio_summary(result)
    public = to_public_portfolio_result(result).model_dump(mode="json")
    assert summary.final_equity == result.metrics.final_equity
    assert summary.max_drawdown_ratio == result.metrics.max_drawdown_ratio
    assert summary.open_position_count == 0
    assert public["summary"]["final_equity"] == "1100"
    assert public["has_equity_curve"] is True


def test_fingerprint_preserves_legacy_and_normalizes_portfolio_decimals() -> None:
    legacy = backtest_config()
    assert (
        backtest_config_fingerprint(legacy)
        == "sha256:911475d75c5eef8ac776128bc96e56de7657d936bc17b1336e897369b8291d87"
    )
    first = backtest_config(
        {
            "quote_asset": "USDC",
            "initial_capital": "10000.00",
            "position_sizing": {"value": "100.0"},
            "fee_rate": "0.0010",
        }
    )
    equivalent = backtest_config(
        {
            "quote_asset": "USDC",
            "initial_capital": "10000",
            "position_sizing": {"value": "100"},
            "fee_rate": "0.001",
        }
    )
    changed = backtest_config(
        {
            "quote_asset": "USDC",
            "initial_capital": "10001",
        }
    )
    assert backtest_config_fingerprint(first) == backtest_config_fingerprint(equivalent)
    assert backtest_config_fingerprint(first) != backtest_config_fingerprint(changed)
    assert backtest_config_fingerprint(first) != backtest_config_fingerprint(legacy)


def test_step_adapter_contract_cannot_receive_forward_outcomes() -> None:
    assert "outcomes" not in signature(build_portfolio_simulation_steps).parameters


def test_openapi_exposes_optional_strict_portfolio_v1_contract() -> None:
    application = FastAPI()
    application.include_router(router)
    schemas = application.openapi()["components"]["schemas"]
    backtest_schema = schemas["BacktestConfig"]
    portfolio_schema = schemas["PortfolioSimulationConfigV1"]
    sizing_schema = schemas["PortfolioPositionSizingConfig"]
    assert "portfolio_simulation" not in backtest_schema.get("required", [])
    assert portfolio_schema["additionalProperties"] is False
    assert sizing_schema["additionalProperties"] is False
    assert portfolio_schema["properties"]["version"]["const"] == 1
