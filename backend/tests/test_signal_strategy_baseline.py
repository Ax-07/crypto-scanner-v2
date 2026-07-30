"""Tests unitaires de la baseline, avec données synthétiques déterministes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.audits.signal_strategy_baseline import (
    DatasetInventory,
    DatasetSelection,
    _simulate_matrix,
    chronological_segments,
    compact_summary,
    inventory_datasets,
    profit_concentration,
    render_markdown,
    select_datasets,
    stable_fingerprint,
    trade_diagnostics,
    write_outputs,
)
from app.domain.portfolio import (
    PortfolioSimulationConfig,
    PortfolioSimulationStep,
    simulate_portfolio,
)

START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _steps(count: int = 24) -> tuple[PortfolioSimulationStep, ...]:
    return tuple(
        PortfolioSimulationStep(
            observation_id=str(index),
            source_open_time=START + timedelta(hours=index),
            decision_time=START + timedelta(hours=index + 1),
            open_price=Decimal(100 + index),
            close_price=Decimal(101 + index),
            accepted=index % 6 in {1, 2, 3},
        )
        for index in range(count)
    )


def _create_candle_database(path: Path, datasets: dict[tuple[str, str], int]) -> None:
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE TABLE candles (
            exchange_id TEXT NOT NULL,
            market_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open_time INTEGER NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            close_time INTEGER,
            is_closed INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
    intervals = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
    for (symbol, timeframe), count in datasets.items():
        interval = intervals[timeframe]
        rows = [
            (
                "binance",
                "spot",
                symbol,
                timeframe,
                index * interval,
                100,
                102,
                99,
                101,
                10,
                (index + 1) * interval - 1,
                1,
                0,
            )
            for index in range(count)
        ]
        connection.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_inventory_empty(tmp_path: Path) -> None:
    database = tmp_path / "empty.sqlite3"
    _create_candle_database(database, {})
    assert inventory_datasets(database) == []


def test_inventory_is_read_only_and_reports_continuity(tmp_path: Path) -> None:
    database = tmp_path / "candles.sqlite3"
    _create_candle_database(database, {("BTC/USDC", "4h"): 600})
    before = _file_hash(database)
    inventory = inventory_datasets(database)
    assert _file_hash(database) == before
    assert len(inventory) == 1
    assert inventory[0].candle_count == 600
    assert inventory[0].gap_count == 0
    assert inventory[0].continuity_ratio == Decimal("1")


def test_selection_one_symbol_and_multiple_timeframes(tmp_path: Path) -> None:
    database = tmp_path / "candles.sqlite3"
    _create_candle_database(
        database,
        {
            ("BTC/USDC", "4h"): 700,
            ("BTC/USDC", "1d"): 600,
            ("LINK/USDC", "4h"): 550,
        },
    )
    selected = select_datasets(database, inventory_datasets(database), mode="full")
    assert [(item.symbol, item.timeframe) for item in selected] == [
        ("BTC/USDC", "4h"),
        ("BTC/USDC", "1d"),
        ("LINK/USDC", "4h"),
    ]


def test_insufficient_dataset_is_not_selected(tmp_path: Path) -> None:
    database = tmp_path / "candles.sqlite3"
    _create_candle_database(database, {("BTC/USDC", "4h"): 499})
    assert select_datasets(database, inventory_datasets(database), mode="full") == []


def test_chronological_segmentation_has_strict_order_and_no_overlap() -> None:
    timestamps = [START + timedelta(hours=index) for index in range(100)]
    development, validation, test = chronological_segments(timestamps)
    assert (development.start_index, development.end_index) == (0, 60)
    assert (validation.start_index, validation.end_index) == (60, 80)
    assert (test.start_index, test.end_index) == (80, 100)
    assert development.end < validation.start < test.start


def test_segmentation_rejects_unsorted_timestamps_anti_lookahead() -> None:
    timestamps = [
        START,
        START + timedelta(hours=1),
        START + timedelta(hours=3),
        START + timedelta(hours=2),
        START + timedelta(hours=4),
    ]
    with pytest.raises(ValueError, match="strictement croissants"):
        chronological_segments(timestamps)


def test_profit_concentration_handles_positive_zero_and_negative_totals() -> None:
    positive = simulate_portfolio(
        symbol="BTC/USDC",
        steps=_steps(),
        config=PortfolioSimulationConfig(quote_asset="USDC", fee_rate=Decimal("0")),
    )
    concentration = profit_concentration(positive.trades)
    assert concentration["best_1"]["pnl"] >= concentration["worst_1"]["pnl"]
    assert concentration["best_5"]["share_interpretation"] in {
        "standard",
        "signed_against_non_positive_total",
        "undefined_zero_total",
    }
    assert profit_concentration([])["best_1"]["share_of_total"] is None


def test_trade_metrics_and_low_sample_are_explicit() -> None:
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=_steps(),
        config=PortfolioSimulationConfig(quote_asset="USDC"),
    )
    diagnostics = trade_diagnostics(result.trades)
    assert diagnostics["pnl"]["count"] == len(result.trades)
    assert diagnostics["return_ratio"]["count"] == len(result.trades)
    assert diagnostics["maximum_winning_streak"] >= 0


def test_cost_sensitivity_keeps_trade_count_and_degrades_equity() -> None:
    steps = _steps()
    matrix = _simulate_matrix(
        symbol="BTC/USDC",
        steps=steps,
        canonical=PortfolioSimulationConfig(quote_asset="USDC"),
    )
    fee_counts = {item["trade_count"] for item in matrix["fees"].values()}
    slippage_counts = {item["trade_count"] for item in matrix["slippage"].values()}
    assert (
        fee_counts
        == slippage_counts
        == {
            len(
                simulate_portfolio(
                    symbol="BTC/USDC",
                    steps=steps,
                    config=PortfolioSimulationConfig(quote_asset="USDC"),
                ).trades
            )
        }
    )
    assert matrix["fees"]["0"]["final_equity"] >= matrix["fees"]["0.002"]["final_equity"]
    assert matrix["slippage"]["0"]["final_equity"] >= matrix["slippage"]["0.002"]["final_equity"]


def test_stable_fingerprint_is_deterministic_and_cost_sensitive() -> None:
    left = stable_fingerprint({"symbol": "BTC/USDC", "fee": "0.001"})
    right = stable_fingerprint({"fee": "0.001", "symbol": "BTC/USDC"})
    changed = stable_fingerprint({"symbol": "BTC/USDC", "fee": "0.002"})
    assert left == right
    assert changed != left


def _minimal_payload() -> dict[str, object]:
    selection = DatasetSelection(
        symbol="BTC/USDC",
        timeframe="4h",
        start=START,
        end=START + timedelta(days=100),
        candle_count=600,
        continuity_ratio=Decimal("1"),
        reason="test",
    )
    metrics = {
        "initial_capital": Decimal("10000"),
        "final_cash": Decimal("10100"),
        "final_equity": Decimal("10100"),
        "net_profit": Decimal("100"),
        "total_return_ratio": Decimal("0.01"),
        "realized_pnl": Decimal("100"),
        "unrealized_pnl": Decimal("0"),
        "total_fees": Decimal("10"),
        "trade_count": 40,
        "winning_trade_count": 22,
        "losing_trade_count": 18,
        "breakeven_trade_count": 0,
        "win_rate": Decimal("0.55"),
        "average_trade_return": Decimal("0.001"),
        "max_drawdown_ratio": Decimal("0.02"),
        "exposure_ratio": Decimal("0.4"),
        "open_position_count": 0,
        "gross_profit": Decimal("300"),
        "gross_loss": Decimal("-200"),
        "profit_factor": Decimal("1.5"),
        "average_win": Decimal("1"),
        "average_loss": Decimal("-1"),
        "largest_win": Decimal("30"),
        "largest_loss": Decimal("-20"),
        "average_trade_duration": Decimal("3"),
    }
    return {
        "version": "signal-strategy-baseline-v1",
        "generated_at": START,
        "git_head": "abcdef0",
        "audit_fingerprint": "sha256:test",
        "inventory": [
            asdict(
                DatasetInventory(
                    exchange_id="binance",
                    market_type="spot",
                    symbol="BTC/USDC",
                    timeframe="4h",
                    first_open_time=START,
                    last_open_time=START + timedelta(days=100),
                    candle_count=600,
                    closed_candle_count=600,
                    gap_count=0,
                    expected_candle_count=600,
                    continuity_ratio=Decimal("1"),
                    source="test.sqlite3",
                )
            )
        ],
        "selected": [asdict(selection)],
        "aggregate_metrics": {"observation_count": 600, "trade_count": 40},
        "results": [
            {
                "dataset": asdict(selection),
                "config_fingerprint": "sha256:config",
                "observation": {"observation_count": 600, "accepted_count": 80},
                "portfolio_metrics": metrics,
                "segments": {
                    name: {"metrics": metrics} for name in ("development", "validation", "test")
                },
                "robustness_status": "prometteur mais instable",
                "sample_warning": None,
            }
        ],
    }


def test_markdown_and_json_generation_are_compact_and_deterministic(
    tmp_path: Path,
) -> None:
    payload = _minimal_payload()
    markdown = render_markdown(payload)
    assert "Résumé exécutif" in markdown
    assert "Phase 7.2" in markdown
    first_markdown, first_json = write_outputs(payload, tmp_path)
    first_bytes = (first_markdown.read_bytes(), first_json.read_bytes())
    write_outputs(payload, tmp_path)
    assert first_bytes == (first_markdown.read_bytes(), first_json.read_bytes())
    parsed = json.loads(first_json.read_text(encoding="utf-8"))
    assert "trades" not in parsed
    assert parsed["datasets"][0]["metrics"]["trade_count"] == 40


def test_compact_summary_excludes_raw_equity_and_trades() -> None:
    summary = compact_summary(_minimal_payload())
    serialized = json.dumps(summary, default=str)
    assert "equity_curve" not in serialized
    assert '"trades"' not in serialized
