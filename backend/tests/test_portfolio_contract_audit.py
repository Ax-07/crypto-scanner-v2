from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.api.backtests import router
from app.database.connection import Database
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.services.portfolio_replay import to_public_portfolio_summary
from tests.test_portfolio_repository import _job, _result

PORTFOLIO_SCHEMA_FIELDS = {
    "PortfolioPositionSizingConfig": {"mode", "value"},
    "PortfolioSimulationConfigV1": {
        "version",
        "quote_asset",
        "initial_capital",
        "position_sizing",
        "execution_policy",
        "fee_rate",
        "slippage_rate",
        "end_of_test_policy",
    },
    "PortfolioSimulationSummary": {
        "version",
        "quote_asset",
        "initial_capital",
        "final_cash",
        "final_equity",
        "net_profit",
        "total_return_ratio",
        "realized_pnl",
        "unrealized_pnl",
        "total_fees",
        "trade_count",
        "winning_trade_count",
        "losing_trade_count",
        "breakeven_trade_count",
        "win_rate",
        "average_trade_return",
        "max_drawdown_ratio",
        "exposure_ratio",
        "open_position_count",
    },
    "PortfolioRunMetadataV1": {
        "version",
        "schema_version",
        "engine_version",
        "quote_asset",
        "summary",
        "details_status",
        "order_count",
        "execution_count",
        "trade_count",
        "equity_point_count",
        "available_after_restart",
    },
    "PortfolioTradeV1": {
        "version",
        "sequence",
        "trade_id",
        "position_id",
        "symbol",
        "quote_asset",
        "entry_observation_id",
        "exit_observation_id",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_fee",
        "exit_fee",
        "gross_exit_proceeds",
        "net_exit_proceeds",
        "realized_pnl",
        "return_ratio",
        "duration_bars",
        "exit_reason",
    },
    "PortfolioEquityPointV1": {
        "version",
        "sequence",
        "timestamp",
        "cash",
        "position_value",
        "equity",
        "realized_pnl_cumulative",
        "unrealized_pnl",
        "fees_cumulative",
        "drawdown_ratio",
    },
    "PortfolioTradePage": {"items", "total", "offset", "limit", "has_more"},
    "PortfolioEquityPage": {
        "items",
        "total",
        "offset",
        "limit",
        "has_more",
        "sampled",
        "source_point_count",
    },
}


def test_portfolio_openapi_contract_snapshot_is_exact_and_explicit() -> None:
    application = FastAPI()
    application.include_router(router)
    schemas = application.openapi()["components"]["schemas"]

    for name, expected_fields in PORTFOLIO_SCHEMA_FIELDS.items():
        schema = schemas[name]
        actual_fields = set(schema["properties"])
        assert actual_fields == expected_fields, (
            f"{name}: champs absents={sorted(expected_fields - actual_fields)}, "
            f"champs inattendus={sorted(actual_fields - expected_fields)}"
        )
        assert schema.get("additionalProperties") is False

    config = schemas["PortfolioSimulationConfigV1"]["properties"]
    for field in ("initial_capital", "fee_rate", "slippage_rate"):
        assert config[field]["type"] == "string", f"{field} doit rester une chaîne JSON"
    assert config["version"]["const"] == 1
    assert config["execution_policy"]["const"] == "next_open"
    assert config["end_of_test_policy"]["const"] == "force_close"

    summary = schemas["PortfolioSimulationSummary"]["properties"]
    nullable = {"win_rate", "average_trade_return"}
    decimal_fields = {
        "initial_capital",
        "final_cash",
        "final_equity",
        "net_profit",
        "total_return_ratio",
        "realized_pnl",
        "unrealized_pnl",
        "total_fees",
        "max_drawdown_ratio",
        "exposure_ratio",
    }
    for field in decimal_fields:
        assert summary[field]["type"] == "string", f"{field} ne doit pas être nullable"
    for field in nullable:
        assert summary[field]["anyOf"] == [{"type": "string"}, {"type": "null"}]

    trade = schemas["PortfolioTradeV1"]["properties"]
    assert trade["exit_reason"]["enum"] == ["validation_lost", "end_of_test"]
    assert trade["exit_observation_id"]["anyOf"] == [
        {"type": "string", "minLength": 1},
        {"type": "null"},
    ]


@pytest.mark.asyncio
async def test_accounting_invariants_survive_persistence_and_restart() -> None:
    result = _result()
    order_ids = {order.id for order in result.orders}
    execution_ids = {execution.id for execution in result.executions}

    assert result.metrics.initial_capital > 0
    assert all(point.cash >= 0 for point in result.equity_curve)
    assert all(execution.order_id in order_ids for execution in result.executions)
    assert all(
        trade.entry_execution_id in execution_ids and trade.exit_execution_id in execution_ids
        for trade in result.trades
    )
    assert result.metrics.total_fees == sum(
        (execution.fee for execution in result.executions), Decimal("0")
    )
    assert result.metrics.realized_pnl == sum(
        (trade.realized_pnl for trade in result.trades), Decimal("0")
    )
    assert result.metrics.final_equity == (
        result.metrics.initial_capital + result.metrics.net_profit
    )
    assert all(point.drawdown_ratio >= 0 for point in result.equity_curve)
    assert result.metrics.max_drawdown_ratio == max(
        point.drawdown_ratio for point in result.equity_curve
    )
    assert result.metrics.trade_count == len(result.trades)

    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "contract-audit.sqlite3"
        database = Database(path)
        await database.initialize()
        await BacktestRepository(database).save_job(_job("contract-audit"))
        repository = PortfolioRepository(database)
        await repository.replace_simulation_result(
            job_id="contract-audit",
            result=result,
            config_fingerprint="sha256:contract-audit",
        )
        metadata = await repository.get_run_metadata("contract-audit")
        assert metadata is not None
        assert metadata.trade_count == len(result.trades)
        assert metadata.equity_point_count == len(result.equity_curve)
        public_before = to_public_portfolio_summary(result).model_dump(mode="json")

        restarted = PortfolioRepository(Database(path))
        restored = await restarted.load_portfolio_simulation_result("contract-audit")
        assert restored == result
        assert restored is not None
        assert restored.metrics == result.metrics
        assert to_public_portfolio_summary(restored).model_dump(mode="json") == public_before
