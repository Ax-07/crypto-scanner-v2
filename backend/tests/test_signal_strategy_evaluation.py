"""Garde-fous méthodologiques et anti-look-ahead de l'audit."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.audits import signal_strategy_baseline as baseline
from app.domain.portfolio import PortfolioSimulationConfig, PortfolioSimulationStep


def test_audit_module_has_no_network_client_dependency() -> None:
    source = inspect.getsource(baseline)
    assert "import requests" not in source
    assert "import httpx" not in source
    assert "import ccxt" not in source


def test_outcomes_are_not_accepted_by_portfolio_sensitivity() -> None:
    signature = inspect.signature(baseline._simulate_matrix)
    assert "outcomes" not in signature.parameters
    assert set(signature.parameters) == {"symbol", "steps", "canonical"}


def test_temporal_bounds_cannot_reuse_a_future_observation() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    timestamps = [start + timedelta(hours=index) for index in range(10)]
    development, validation, test = baseline.chronological_segments(timestamps)
    assert development.end_index == validation.start_index
    assert validation.end_index == test.start_index
    assert set(range(development.start_index, development.end_index)).isdisjoint(
        range(validation.start_index, test.end_index)
    )


def test_sensitivity_does_not_mutate_steps_or_canonical_config() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    steps = tuple(
        PortfolioSimulationStep(
            observation_id=str(index),
            source_open_time=start + timedelta(hours=index),
            decision_time=start + timedelta(hours=index + 1),
            open_price=Decimal(100 + index),
            close_price=Decimal(101 + index),
            accepted=index % 4 in {1, 2},
        )
        for index in range(12)
    )
    config = PortfolioSimulationConfig(quote_asset="USDC")
    before = (steps, config)
    first = baseline._simulate_matrix(symbol="BTC/USDC", steps=steps, canonical=config)
    second = baseline._simulate_matrix(symbol="BTC/USDC", steps=steps, canonical=config)
    assert before == (steps, config)
    assert baseline.stable_fingerprint(first) == baseline.stable_fingerprint(second)


def test_predefined_confluence_buckets_are_present_in_source() -> None:
    source = inspect.getsource(baseline.confluence_diagnostics)
    assert "low:<40" in source
    assert "medium:40-69.999" in source
    assert "high:>=70" in source
