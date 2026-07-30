from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.portfolio import (
    OrderSide,
    PortfolioValidationError,
    StrategyAction,
    StrategyReason,
    calculate_percent_cash_allocation,
    evaluate_accepted_state_transition,
)


@pytest.mark.parametrize(
    ("previous", "current", "position", "expected"),
    [
        (False, False, False, StrategyAction.HOLD),
        (False, True, False, StrategyAction.ENTER_LONG),
        (True, True, True, StrategyAction.HOLD),
        (True, False, True, StrategyAction.EXIT_LONG),
    ],
)
def test_accepted_state_transitions(
    previous: bool,
    current: bool,
    position: bool,
    expected: StrategyAction,
) -> None:
    intent = evaluate_accepted_state_transition(
        previous_accepted=previous,
        current_accepted=current,
        has_open_position=position,
        pending_order_side=None,
    )
    assert intent.action is expected


def test_strategy_holds_for_existing_position_or_pending_order() -> None:
    already_long = evaluate_accepted_state_transition(
        previous_accepted=False,
        current_accepted=True,
        has_open_position=True,
        pending_order_side=None,
    )
    pending = evaluate_accepted_state_transition(
        previous_accepted=False,
        current_accepted=True,
        has_open_position=False,
        pending_order_side=OrderSide.BUY,
    )
    flat_exit = evaluate_accepted_state_transition(
        previous_accepted=True,
        current_accepted=False,
        has_open_position=False,
        pending_order_side=None,
    )
    assert already_long.action is StrategyAction.HOLD
    assert pending.reason is StrategyReason.ORDER_ALREADY_PENDING
    assert flat_exit.action is StrategyAction.HOLD


@pytest.mark.parametrize(
    ("cash", "percent", "expected"),
    [
        ("1000", "100", "1000"),
        ("1000", "50", "500"),
        ("1000", "0.0001", "0.001"),
        ("0", "100", "0"),
    ],
)
def test_percent_cash_sizing(cash: str, percent: str, expected: str) -> None:
    assert calculate_percent_cash_allocation(
        available_cash=Decimal(cash),
        position_size_percent=Decimal(percent),
    ) == Decimal(expected)


@pytest.mark.parametrize("percent", ["0", "-1", "100.01"])
def test_percent_cash_sizing_rejects_invalid_percent(percent: str) -> None:
    with pytest.raises((PortfolioValidationError, ValueError)):
        calculate_percent_cash_allocation(
            available_cash=Decimal("100"),
            position_size_percent=Decimal(percent),
        )
