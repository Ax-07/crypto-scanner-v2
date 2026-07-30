from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain.portfolio import (
    ExitReason,
    OrderRejectionReason,
    OrderSide,
    OrderStatus,
    PortfolioSimulationConfig,
    PortfolioValidationError,
    simulate_portfolio,
)
from tests.domain.portfolio.conftest import make_steps


def config(**updates: object) -> PortfolioSimulationConfig:
    values: dict[str, object] = {
        "quote_asset": "USDC",
        "initial_capital": Decimal("1000"),
        "position_size_percent": Decimal("100"),
        "fee_rate": Decimal("0"),
        "slippage_rate": Decimal("0"),
    }
    values.update(updates)
    return PortfolioSimulationConfig(**values)  # type: ignore[arg-type]


def test_manual_entry_and_exit_without_friction() -> None:
    steps = make_steps(
        [True, False, False],
        opens=["90", "100", "110"],
        closes=["95", "105", "110"],
    )
    result = simulate_portfolio(symbol="BTC/USDC", steps=steps, config=config())
    trade = result.trades[0]
    assert trade.entry_price == Decimal("100")
    assert trade.exit_price == Decimal("110")
    assert trade.quantity == Decimal("10")
    assert trade.realized_pnl == Decimal("100")
    assert trade.return_ratio == Decimal("0.1")
    assert trade.duration_bars == 1
    assert result.final_cash == Decimal("1100")
    assert result.metrics.total_return_ratio == Decimal("0.1")


def test_manual_fee_oracle() -> None:
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=make_steps(
            [True, False, False],
            opens=["90", "100", "110"],
            closes=["95", "105", "110"],
        ),
        config=config(fee_rate=Decimal("0.01")),
    )
    trade = result.trades[0]
    entry_notional = Decimal("1000") / Decimal("1.01")
    entry_fee = entry_notional * Decimal("0.01")
    quantity = entry_notional / Decimal("100")
    gross = quantity * Decimal("110")
    exit_fee = gross * Decimal("0.01")
    net = gross - exit_fee
    realized = net - entry_notional - entry_fee
    assert trade.entry_fee == entry_fee
    assert trade.quantity == quantity
    assert trade.gross_exit_proceeds == gross
    assert trade.exit_fee == exit_fee
    assert trade.net_exit_proceeds == net
    assert trade.realized_pnl == realized
    assert trade.return_ratio == realized / Decimal("1000")
    assert result.final_cash == net


def test_manual_slippage_and_losing_trade() -> None:
    slipped = simulate_portfolio(
        symbol="BTC/USDC",
        steps=make_steps(
            [True, False, False],
            opens=["90", "100", "110"],
            closes=["95", "105", "110"],
        ),
        config=config(slippage_rate=Decimal("0.01")),
    )
    assert slipped.trades[0].entry_price == Decimal("101")
    assert slipped.trades[0].exit_price == Decimal("108.90")
    assert slipped.final_cash == Decimal("1000") / Decimal("101") * Decimal("108.90")

    losing = simulate_portfolio(
        symbol="BTC/USDC",
        steps=make_steps(
            [True, False, False],
            opens=["90", "100", "90"],
            closes=["95", "95", "90"],
        ),
        config=config(),
    )
    assert losing.final_cash == Decimal("900")
    assert losing.metrics.losing_trade_count == 1
    assert losing.metrics.max_drawdown_ratio == Decimal("0.1")


def test_two_compounded_trades_and_deterministic_ids() -> None:
    steps = make_steps(
        [True, False, False, True, False, False],
        opens=["90", "100", "110", "110", "110", "99"],
        closes=["95", "105", "110", "110", "105", "99"],
    )
    first = simulate_portfolio(symbol="BTC/USDC", steps=steps, config=config())
    second = simulate_portfolio(symbol="BTC/USDC", steps=steps, config=config())
    assert first == second
    assert first.final_cash == Decimal("990")
    assert [trade.return_ratio for trade in first.trades] == [
        Decimal("0.1"),
        Decimal("-0.1"),
    ]
    assert [order.id for order in first.orders] == [
        "order-000001",
        "order-000002",
        "order-000003",
        "order-000004",
    ]
    assert [execution.id for execution in first.executions] == [
        "execution-000001",
        "execution-000002",
        "execution-000003",
        "execution-000004",
    ]


def test_force_close_is_administrative_and_replaces_last_equity() -> None:
    steps = make_steps(
        [True, True],
        opens=["90", "100"],
        closes=["95", "110"],
    )
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=steps,
        config=config(fee_rate=Decimal("0.01"), slippage_rate=Decimal("0.01")),
    )
    trade = result.trades[0]
    assert trade.exit_reason is ExitReason.END_OF_TEST
    assert trade.exit_observation_id is None
    assert trade.exit_time == steps[-1].decision_time
    assert result.final_open_position is None
    assert result.equity_curve[-1].cash == result.final_cash
    assert result.equity_curve[-1].position_value == Decimal("0")
    assert result.equity_curve[-1].equity == result.final_equity
    assert result.orders[-1].observation_id is None
    assert result.orders[-1].status is OrderStatus.EXECUTED


def test_last_entry_is_rejected_without_fabricating_a_trade() -> None:
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=make_steps([False, True], opens=["100", "100"]),
        config=config(),
    )
    assert len(result.orders) == 1
    assert result.orders[0].side is OrderSide.BUY
    assert result.orders[0].status is OrderStatus.REJECTED
    assert result.orders[0].rejection_reason is OrderRejectionReason.END_OF_DATA
    assert result.executions == ()
    assert result.trades == ()
    assert result.final_cash == Decimal("1000")


def test_last_strategic_exit_expires_then_force_close_wins() -> None:
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=make_steps(
            [True, False],
            opens=["90", "100"],
            closes=["95", "110"],
        ),
        config=config(),
    )
    assert result.orders[1].rejection_reason is OrderRejectionReason.END_OF_DATA
    assert result.orders[2].status is OrderStatus.EXECUTED
    assert result.trades[0].exit_reason is ExitReason.END_OF_TEST
    assert result.trades[0].exit_observation_id is None


def test_event_order_and_exact_timestamps() -> None:
    steps = make_steps(
        [True, False, False],
        opens=["90", "100", "110"],
        closes=["95", "105", "110"],
    )
    result = simulate_portfolio(symbol="BTC/USDC", steps=steps, config=config())
    assert result.orders[0].intent_time == steps[0].decision_time
    assert result.executions[0].timestamp == steps[1].source_open_time
    assert result.equity_curve[1].timestamp == steps[1].decision_time
    assert result.orders[1].intent_time == steps[1].decision_time
    assert result.executions[1].timestamp == steps[2].source_open_time
    assert result.trades[0].entry_time == steps[1].source_open_time
    assert result.trades[0].exit_time == steps[2].source_open_time


def test_future_close_cannot_change_prior_next_open_execution() -> None:
    """Anti-look-ahead : le close futur ne modifie pas le fill à son open."""
    steps = make_steps(
        [True, False, False],
        opens=["90", "100", "110"],
        closes=["95", "105", "110"],
    )
    mutated = list(steps)
    mutated[1] = replace(mutated[1], close_price=Decimal("999999"))
    before = simulate_portfolio(symbol="BTC/USDC", steps=steps, config=config())
    after = simulate_portfolio(symbol="BTC/USDC", steps=mutated, config=config())
    assert before.executions[0] == after.executions[0]
    assert before.orders[:2] == after.orders[:2]
    assert before.equity_curve[1] != after.equity_curve[1]


def test_repeated_acceptances_create_no_pyramiding() -> None:
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=make_steps([False, True, True, True, False, False]),
        config=config(),
    )
    assert [order.side for order in result.orders] == [OrderSide.BUY, OrderSide.SELL]
    assert len(result.trades) == 1


def test_input_sequence_is_not_silently_sorted() -> None:
    steps = make_steps([False, True])
    with pytest.raises(PortfolioValidationError, match="croissants"):
        simulate_portfolio(symbol="BTC/USDC", steps=list(reversed(steps)), config=config())
    with pytest.raises(PortfolioValidationError, match="uniques"):
        simulate_portfolio(
            symbol="BTC/USDC",
            steps=[steps[0], replace(steps[1], observation_id=steps[0].observation_id)],
            config=config(),
        )
