from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from app.domain.portfolio import PortfolioSimulationConfig, simulate_portfolio
from tests.domain.portfolio.conftest import make_steps


def test_no_trade_metrics_have_explicit_empty_values() -> None:
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=make_steps([False, False], closes=["100", "100"]),
        config=PortfolioSimulationConfig(
            quote_asset="USDC",
            initial_capital=Decimal("1000"),
            fee_rate=Decimal("0"),
        ),
    )
    metrics = result.metrics
    assert metrics.final_cash == Decimal("1000")
    assert metrics.final_equity == Decimal("1000")
    assert metrics.net_profit == Decimal("0")
    assert metrics.total_return_ratio == Decimal("0")
    assert metrics.realized_pnl == Decimal("0")
    assert metrics.unrealized_pnl == Decimal("0")
    assert metrics.trade_count == 0
    assert metrics.win_rate is None
    assert metrics.average_trade_return is None
    assert metrics.max_drawdown_ratio == Decimal("0")
    assert metrics.exposure_ratio == Decimal("0")


def test_win_loss_breakeven_average_fees_and_exposure_are_consistent() -> None:
    steps = make_steps(
        [True, False, False, True, False, False, True, False, False],
        opens=["90", "100", "110", "110", "110", "99", "99", "100", "100"],
        closes=["95", "105", "110", "110", "105", "99", "99", "100", "100"],
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
    metrics = result.metrics
    assert metrics.trade_count == 3
    assert metrics.winning_trade_count == 1
    assert metrics.losing_trade_count == 1
    assert metrics.breakeven_trade_count == 1
    assert metrics.win_rate == Decimal("1") / Decimal("3")
    assert metrics.average_trade_return == Decimal("0")
    assert metrics.realized_pnl == sum(
        (trade.realized_pnl for trade in result.trades), Decimal("0")
    )
    assert metrics.total_fees == sum(
        (execution.fee for execution in result.executions), Decimal("0")
    )
    assert metrics.exposure_ratio == Decimal("3") / Decimal("9")


def test_portfolio_package_has_no_forbidden_imports() -> None:
    package = Path(__file__).parents[3] / "app" / "domain" / "portfolio"
    forbidden = ("fastapi", "ccxt", "sqlite", "frontend", "forwardoutcome", "services.backtest")
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ] + [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        lowered = " ".join(imports).lower()
        assert not any(name in lowered for name in forbidden), path.name
