from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.portfolio import (
    PortfolioExecutionError,
    PortfolioValidationError,
    calculate_entry_execution,
    calculate_exit_execution,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_entry_includes_fees_in_allocation_and_never_makes_cash_negative() -> None:
    result = calculate_entry_execution(
        execution_id="execution-000001",
        order_id="order-000001",
        timestamp=NOW,
        reference_price=Decimal("100"),
        allocated_cash=Decimal("1000"),
        cash_before=Decimal("1000"),
        fee_rate=Decimal("0.01"),
        slippage_rate=Decimal("0"),
    )
    assert result.execution.execution_price == Decimal("100")
    assert result.execution.gross_notional == Decimal("1000") / Decimal("1.01")
    assert result.execution.fee == result.execution.gross_notional * Decimal("0.01")
    assert result.execution.quantity == result.execution.gross_notional / Decimal("100")
    assert result.cash_after == Decimal("0")


def test_entry_slippage_is_adverse_and_partial_sizing_leaves_cash() -> None:
    result = calculate_entry_execution(
        execution_id="execution-000001",
        order_id="order-000001",
        timestamp=NOW,
        reference_price=Decimal("100"),
        allocated_cash=Decimal("500"),
        cash_before=Decimal("1000"),
        fee_rate=Decimal("0"),
        slippage_rate=Decimal("0.01"),
    )
    assert result.execution.execution_price == Decimal("101")
    assert result.execution.quantity == Decimal("500") / Decimal("101")
    assert result.cash_after == Decimal("500")


def test_exit_applies_adverse_slippage_and_fee() -> None:
    result = calculate_exit_execution(
        execution_id="execution-000002",
        order_id="order-000002",
        timestamp=NOW,
        reference_price=Decimal("110"),
        quantity=Decimal("10"),
        cash_before=Decimal("0"),
        fee_rate=Decimal("0.01"),
        slippage_rate=Decimal("0.01"),
    )
    assert result.execution.execution_price == Decimal("108.90")
    assert result.execution.gross_notional == Decimal("1089.00")
    assert result.execution.fee == Decimal("10.8900")
    assert result.net_proceeds == Decimal("1078.1100")
    assert result.cash_after == result.net_proceeds


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity"])
def test_entry_and_exit_reject_invalid_prices(price: str) -> None:
    common = {
        "timestamp": NOW,
        "reference_price": Decimal(price),
        "cash_before": Decimal("1000"),
        "fee_rate": Decimal("0"),
        "slippage_rate": Decimal("0"),
    }
    with pytest.raises(PortfolioValidationError):
        calculate_entry_execution(
            execution_id="execution-000001",
            order_id="order-000001",
            allocated_cash=Decimal("100"),
            **common,
        )
    with pytest.raises(PortfolioValidationError):
        calculate_exit_execution(
            execution_id="execution-000001",
            order_id="order-000001",
            quantity=Decimal("1"),
            **common,
        )


def test_entry_rejects_allocation_above_cash_and_exit_rejects_zero_quantity() -> None:
    with pytest.raises(PortfolioExecutionError):
        calculate_entry_execution(
            execution_id="execution-000001",
            order_id="order-000001",
            timestamp=NOW,
            reference_price=Decimal("100"),
            allocated_cash=Decimal("1001"),
            cash_before=Decimal("1000"),
            fee_rate=Decimal("0"),
            slippage_rate=Decimal("0"),
        )
    with pytest.raises(PortfolioValidationError):
        calculate_exit_execution(
            execution_id="execution-000001",
            order_id="order-000001",
            timestamp=NOW,
            reference_price=Decimal("100"),
            quantity=Decimal("0"),
            cash_before=Decimal("0"),
            fee_rate=Decimal("0"),
            slippage_rate=Decimal("0"),
        )
