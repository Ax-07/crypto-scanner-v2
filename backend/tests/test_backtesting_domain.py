from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.settings import ScanConfig
from app.domain.backtesting import (
    build_analytics,
    calculate_forward_outcomes,
    evaluate_information_set,
)
from app.models.backtest import BacktestConfig, ForwardOutcome, SignalObservation
from tests.fixtures.synthetic_backtest_v1 import DATASET_VERSION, candles


def signal_config() -> ScanConfig:
    return ScanConfig(
        timeframe="1m",
        min_ohlcv_bars=60,
        use_ma=False,
        ma_timeframes=[],
        min_trend_score=0,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=False,
        rsi_threshold=45,
        min_confluence_score=0,
    )


def backtest_config(**updates) -> BacktestConfig:
    rows = candles()
    values = {
        "symbols": ["SYN/USDC"],
        "start": datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
        "end": datetime.fromtimestamp(rows[100].open_time / 1_000, tz=timezone.utc),
        "signal_config": signal_config(),
        "horizons": [1, 3, 6],
    }
    values.update(updates)
    return BacktestConfig(**values)


def test_dataset_contract_is_versioned() -> None:
    golden = json.loads(
        (Path(__file__).parent / "fixtures" / "synthetic_backtest_v1_golden.json").read_text()
    )
    assert golden["dataset_version"] == DATASET_VERSION
    assert golden["decision_bars"] == 20
    rows = candles()
    index = golden["decision_index"]
    decision = rows[index].close_time
    assert decision is not None
    observation = evaluate_information_set(
        job_id="golden-v1",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=rows[index - 59 : index + 1],
        trend_candles={},
        config=signal_config(),
        dataset_version=DATASET_VERSION,
    )
    actual_observation = observation.model_dump(mode="json", include=set(golden["observation"]))
    assert actual_observation == golden["observation"]
    outcomes = calculate_forward_outcomes(1, rows, index, backtest_config())
    actual_outcomes = [
        item.model_dump(mode="json", include=set(golden["outcomes"][0])) for item in outcomes
    ]
    assert actual_outcomes == golden["outcomes"]


def test_future_mutation_cannot_change_signal() -> None:
    rows = candles()
    index = 90
    decision = rows[index].close_time
    assert decision is not None
    before = evaluate_information_set(
        job_id="causal",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=rows[index - 59 : index + 1],
        trend_candles={},
        config=signal_config(),
    )
    future = list(rows)
    changed = future[index + 1]
    future[index + 1] = type(changed)(
        changed.exchange_id,
        changed.market_type,
        changed.symbol,
        changed.timeframe,
        changed.open_time,
        changed.open,
        changed.high * 100,
        changed.low / 100,
        changed.close * 100,
        changed.volume,
        changed.close_time,
        changed.is_closed,
    )
    after = evaluate_information_set(
        job_id="causal",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=future[index - 59 : index + 1],
        trend_candles={},
        config=signal_config(),
    )
    assert before.model_dump(exclude={"decision_time"}) == after.model_dump(
        exclude={"decision_time"}
    )


def test_future_mutation_cannot_change_indicator_signals() -> None:
    """Anti-look-ahead: la mutation de bougies futures ne doit pas changer les
    signaux structures `indicator_signals` (rsi/macd/bollinger/stochastic),
    exactement comme pour les autres champs de SignalObservation."""
    rows = candles()
    index = 90
    decision = rows[index].close_time
    assert decision is not None
    config = signal_config().model_copy(
        update={
            "use_rsi": True,
            "use_macd": True,
            "use_bollinger": True,
            "use_stochastic": True,
        }
    )
    before = evaluate_information_set(
        job_id="causal-signals",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=rows[index - 59 : index + 1],
        trend_candles={},
        config=config,
    )
    assert before.indicator_signals
    assert set(before.indicator_signals.keys()) >= {"rsi", "macd", "bollinger", "stochastic"}

    future = list(rows)
    changed = future[index + 1]
    future[index + 1] = type(changed)(
        changed.exchange_id,
        changed.market_type,
        changed.symbol,
        changed.timeframe,
        changed.open_time,
        changed.open,
        changed.high * 100,
        changed.low / 100,
        changed.close * 100,
        changed.volume,
        changed.close_time,
        changed.is_closed,
    )
    after = evaluate_information_set(
        job_id="causal-signals",
        symbol="SYN/USDC",
        decision_time_ms=decision,
        primary=future[index - 59 : index + 1],
        trend_candles={},
        config=config,
    )
    assert before.indicator_signals == after.indicator_signals


def test_information_set_rejects_future_primary_or_higher_timeframe() -> None:
    rows = candles()
    decision = rows[70].close_time
    assert decision is not None
    with pytest.raises(ValueError, match="lookahead"):
        evaluate_information_set(
            job_id="future",
            symbol="SYN/USDC",
            decision_time_ms=decision,
            primary=rows[11:72],
            trend_candles={},
            config=signal_config(),
        )
    config = signal_config().model_copy(
        update={"use_ma": True, "ma_timeframes": ["1m"], "min_trend_score": 0}
    )
    with pytest.raises(ValueError, match="lookahead"):
        evaluate_information_set(
            job_id="future",
            symbol="SYN/USDC",
            decision_time_ms=decision,
            primary=rows[11:71],
            trend_candles={"1m": rows[11:72]},
            config=config,
        )


def test_next_open_fees_and_censoring_are_explicit() -> None:
    rows = candles(10)
    config = backtest_config(entry_policy="next_open", horizons=[1, 20], fee_bps=10, slippage_bps=5)
    outcomes = calculate_forward_outcomes(1, rows, 5, config)
    first = outcomes[0]
    assert first.entry_price == rows[6].open
    assert first.exit_price == rows[7].close
    assert first.net_return is not None and first.gross_return is not None
    assert first.net_return < first.gross_return
    assert outcomes[1].censored
    assert outcomes[1].censor_reason == "fin_de_serie"


def test_correlations_use_pairwise_available_rows_without_imputation() -> None:
    config = backtest_config()
    observations = [
        SignalObservation(
            id=index,
            job_id="stats",
            symbol="SYN/USDC",
            timeframe="1m",
            decision_time=datetime.now(timezone.utc),
            accepted=True,
            close=100,
            rsi=value,
            confluence_factors={"rsi": value / 100 if value is not None else None},
            availability={"rsi": "available" if value is not None else "insufficient_data"},
        )
        for index, value in enumerate((20.0, None, 40.0), start=1)
    ]
    outcomes = [
        ForwardOutcome(
            observation_id=index,
            horizon=1,
            entry_policy="signal_close",
            net_return=value,
        )
        for index, value in enumerate((0.1, 0.2, -0.1), start=1)
    ]
    _, correlations, _ = build_analytics(observations, outcomes, config, [])
    matrix = correlations["by_horizon"]["1"]
    assert matrix["pair_counts"]["rsi"]["outcome"] == 2
    assert correlations["availability"]["rsi"] == {
        "available": 2,
        "insufficient_data": 1,
    }
