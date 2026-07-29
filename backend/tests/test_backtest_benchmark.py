"""Benchmark opt-in, exclu du chemin de test normal."""

from __future__ import annotations

import os
import time

import pytest

from app.domain.backtesting import evaluate_information_set
from tests.fixtures.synthetic_backtest_v1 import candles
from tests.test_backtesting_domain import signal_config


@pytest.mark.skipif(
    os.environ.get("RUN_BACKTEST_BENCHMARK") != "1",
    reason="benchmark non bloquant; activer avec RUN_BACKTEST_BENCHMARK=1",
)
def test_causal_evaluator_benchmark() -> None:
    rows = candles(2_100)
    started = time.perf_counter()
    for index in range(60, len(rows)):
        evaluate_information_set(
            job_id="benchmark",
            symbol="SYN/USDC",
            decision_time_ms=rows[index].close_time or rows[index].open_time,
            primary=rows[index - 59 : index + 1],
            trend_candles={},
            config=signal_config(),
        )
    elapsed = time.perf_counter() - started
    print(f"causal_evaluator observations={len(rows) - 60} elapsed_s={elapsed:.3f}")
