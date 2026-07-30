"""Stratégie pure ``accepted_state_transition_v1``."""

from __future__ import annotations

from app.domain.portfolio.types import (
    OrderSide,
    StrategyAction,
    StrategyIntent,
    StrategyReason,
)


def evaluate_accepted_state_transition(
    *,
    previous_accepted: bool,
    current_accepted: bool,
    has_open_position: bool,
    pending_order_side: OrderSide | None,
) -> StrategyIntent:
    """Transforme l'état accepted en intention long-only, sans calcul de prix."""
    if pending_order_side is not None:
        return StrategyIntent(StrategyAction.HOLD, StrategyReason.ORDER_ALREADY_PENDING)
    if has_open_position:
        if previous_accepted and not current_accepted:
            return StrategyIntent(StrategyAction.EXIT_LONG, StrategyReason.VALIDATION_LOST)
        reason = (
            StrategyReason.POSITION_ALREADY_OPEN
            if current_accepted
            else StrategyReason.VALIDATION_UNCHANGED
        )
        return StrategyIntent(StrategyAction.HOLD, reason)
    if not previous_accepted and current_accepted:
        return StrategyIntent(StrategyAction.ENTER_LONG, StrategyReason.VALIDATION_GAINED)
    return StrategyIntent(StrategyAction.HOLD, StrategyReason.VALIDATION_UNCHANGED)
