"""Comptabilité pure des positions, trades et valorisations."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app.domain.portfolio.decimal_utils import DECIMAL_PRECISION, ZERO
from app.domain.portfolio.execution import ExitExecutionCalculation
from app.domain.portfolio.types import (
    ExitReason,
    SimulatedExecution,
    SimulatedPosition,
    SimulatedTrade,
)


def open_long_position(
    *,
    position_id: str,
    symbol: str,
    quote_asset: str,
    observation_id: str,
    execution: SimulatedExecution,
    opened_bar_index: int,
) -> SimulatedPosition:
    """Construit la position longue issue d'une exécution d'achat."""
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        total_cost = execution.gross_notional + execution.fee
    return SimulatedPosition(
        id=position_id,
        symbol=symbol,
        quote_asset=quote_asset,
        opened_at=execution.timestamp,
        entry_observation_id=observation_id,
        entry_order_id=execution.order_id,
        entry_execution_id=execution.id,
        quantity=execution.quantity,
        entry_execution_price=execution.execution_price,
        entry_notional=execution.gross_notional,
        entry_fee=execution.fee,
        total_entry_cost=total_cost,
        opened_bar_index=opened_bar_index,
    )


def close_long_position(
    *,
    trade_id: str,
    position: SimulatedPosition,
    exit_observation_id: str | None,
    exit_calculation: ExitExecutionCalculation,
    exit_reason: ExitReason,
    duration_bars: int,
) -> SimulatedTrade:
    """Clôture entièrement une position et calcule son P&L réalisé."""
    execution = exit_calculation.execution
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        realized_pnl = exit_calculation.net_proceeds - position.total_entry_cost
        return_ratio = realized_pnl / position.total_entry_cost
    return SimulatedTrade(
        id=trade_id,
        position_id=position.id,
        symbol=position.symbol,
        quote_asset=position.quote_asset,
        entry_observation_id=position.entry_observation_id,
        exit_observation_id=exit_observation_id,
        entry_order_id=position.entry_order_id,
        exit_order_id=execution.order_id,
        entry_execution_id=position.entry_execution_id,
        exit_execution_id=execution.id,
        entry_time=position.opened_at,
        exit_time=execution.timestamp,
        entry_price=position.entry_execution_price,
        exit_price=execution.execution_price,
        quantity=position.quantity,
        entry_fee=position.entry_fee,
        exit_fee=execution.fee,
        gross_exit_proceeds=execution.gross_notional,
        net_exit_proceeds=exit_calculation.net_proceeds,
        realized_pnl=realized_pnl,
        return_ratio=return_ratio,
        duration_bars=duration_bars,
        exit_reason=exit_reason,
    )


def value_open_position(
    position: SimulatedPosition | None, mark_price: Decimal
) -> tuple[Decimal, Decimal]:
    """Valorise au close brut, sans frais ni slippage de sortie hypothétiques."""
    if position is None:
        return ZERO, ZERO
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        market_value = position.quantity * mark_price
        unrealized_pnl = market_value - position.total_entry_cost
    return market_value, unrealized_pnl
