"""Boucle événementielle déterministe du simulateur de portefeuille v1."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from typing import Sequence

from app.domain.portfolio.accounting import (
    close_long_position,
    open_long_position,
    value_open_position,
)
from app.domain.portfolio.decimal_utils import (
    DECIMAL_PRECISION,
    ZERO,
    PortfolioExecutionError,
    PortfolioInvariantError,
    PortfolioValidationError,
)
from app.domain.portfolio.execution import (
    calculate_entry_execution,
    calculate_exit_execution,
)
from app.domain.portfolio.metrics import calculate_drawdown, calculate_portfolio_metrics
from app.domain.portfolio.sizing import calculate_percent_cash_allocation
from app.domain.portfolio.strategy import evaluate_accepted_state_transition
from app.domain.portfolio.types import (
    EquityPoint,
    ExecutionPolicy,
    ExitReason,
    OrderRejectionReason,
    OrderSide,
    OrderStatus,
    PortfolioSimulationConfig,
    PortfolioSimulationResult,
    PortfolioSimulationStep,
    SimulatedExecution,
    SimulatedOrder,
    SimulatedPosition,
    SimulatedTrade,
    StrategyAction,
)


@dataclass(slots=True)
class _MutablePortfolioState:
    cash: Decimal
    open_position: SimulatedPosition | None
    pending_order_index: int | None
    realized_pnl: Decimal
    total_fees: Decimal
    completed_trades: list[SimulatedTrade]


@dataclass(slots=True)
class _IdSequence:
    order: int = 0
    execution: int = 0
    position: int = 0
    trade: int = 0

    def next_order(self) -> str:
        self.order += 1
        return f"order-{self.order:06d}"

    def next_execution(self) -> str:
        self.execution += 1
        return f"execution-{self.execution:06d}"

    def next_position(self) -> str:
        self.position += 1
        return f"position-{self.position:06d}"

    def next_trade(self) -> str:
        self.trade += 1
        return f"trade-{self.trade:06d}"


def _validate_inputs(
    symbol: str,
    steps: Sequence[PortfolioSimulationStep],
) -> None:
    if not isinstance(symbol, str) or not symbol.strip():
        raise PortfolioValidationError("symbol ne doit pas être vide")
    if not steps:
        raise PortfolioValidationError("La simulation exige au moins une étape")
    observation_ids: set[str] = set()
    previous: PortfolioSimulationStep | None = None
    for step in steps:
        if not isinstance(step, PortfolioSimulationStep):
            raise PortfolioValidationError("Chaque étape doit être un PortfolioSimulationStep")
        if step.observation_id in observation_ids:
            raise PortfolioValidationError("Les observation_id doivent être uniques")
        observation_ids.add(step.observation_id)
        if previous is not None:
            if step.decision_time <= previous.decision_time:
                raise PortfolioValidationError(
                    "Les decision_time doivent être strictement croissants"
                )
            if step.source_open_time <= previous.source_open_time:
                raise PortfolioValidationError(
                    "Les source_open_time doivent être strictement croissants"
                )
            if step.source_open_time < previous.decision_time:
                raise PortfolioValidationError(
                    "Une ouverture suivante ne peut pas précéder la décision précédente"
                )
        previous = step


def _assert_invariants(
    *,
    state: _MutablePortfolioState,
    orders: Sequence[SimulatedOrder],
    executions: Sequence[SimulatedExecution],
) -> None:
    values = (state.cash, state.realized_pnl, state.total_fees)
    if any(not value.is_finite() for value in values):
        raise PortfolioInvariantError("Valeur comptable non finie")
    if state.cash < ZERO or state.total_fees < ZERO:
        raise PortfolioInvariantError("Cash ou frais négatifs")
    if state.open_position is not None:
        position = state.open_position
        if position.quantity <= ZERO or position.total_entry_cost <= ZERO:
            raise PortfolioInvariantError("Position ouverte invalide")
    pending = [order for order in orders if order.status is OrderStatus.PENDING]
    if len(pending) > 1:
        raise PortfolioInvariantError("Plus d'un ordre est en attente")
    if state.pending_order_index is None and pending:
        raise PortfolioInvariantError("Ordre en attente non référencé")
    order_ids = {order.id for order in orders}
    if any(execution.order_id not in order_ids for execution in executions):
        raise PortfolioInvariantError("Exécution sans ordre")
    if len({execution.order_id for execution in executions}) != len(executions):
        raise PortfolioInvariantError("Ordre exécuté plusieurs fois")


def _operational_rejection(
    *,
    side: OrderSide,
    state: _MutablePortfolioState,
) -> OrderRejectionReason | None:
    if state.pending_order_index is not None:
        return (
            OrderRejectionReason.ENTRY_ORDER_ALREADY_PENDING
            if side is OrderSide.BUY
            else OrderRejectionReason.EXIT_ORDER_ALREADY_PENDING
        )
    if side is OrderSide.BUY and state.open_position is not None:
        return OrderRejectionReason.POSITION_ALREADY_OPEN
    if side is OrderSide.SELL and state.open_position is None:
        return OrderRejectionReason.NO_OPEN_POSITION
    if side is OrderSide.BUY and state.cash <= ZERO:
        return OrderRejectionReason.INSUFFICIENT_CASH
    return None


def _append_order(
    *,
    orders: list[SimulatedOrder],
    ids: _IdSequence,
    state: _MutablePortfolioState,
    side: OrderSide,
    step: PortfolioSimulationStep,
    config: PortfolioSimulationConfig,
) -> None:
    rejection = _operational_rejection(side=side, state=state)
    requested_cash = (
        calculate_percent_cash_allocation(
            available_cash=state.cash,
            position_size_percent=config.position_size_percent,
        )
        if side is OrderSide.BUY
        else None
    )
    if side is OrderSide.BUY and requested_cash == ZERO and rejection is None:
        rejection = OrderRejectionReason.BELOW_INTERNAL_MINIMUM
    order = SimulatedOrder(
        id=ids.next_order(),
        observation_id=step.observation_id,
        side=side,
        intent_time=step.decision_time,
        execution_policy=ExecutionPolicy.NEXT_OPEN,
        requested_cash=requested_cash,
        status=OrderStatus.REJECTED if rejection is not None else OrderStatus.PENDING,
        rejection_reason=rejection,
    )
    orders.append(order)
    if order.status is OrderStatus.PENDING:
        state.pending_order_index = len(orders) - 1


def _execute_pending(
    *,
    symbol: str,
    step: PortfolioSimulationStep,
    step_index: int,
    config: PortfolioSimulationConfig,
    state: _MutablePortfolioState,
    orders: list[SimulatedOrder],
    executions: list[SimulatedExecution],
    ids: _IdSequence,
) -> None:
    if state.pending_order_index is None:
        return
    order_index = state.pending_order_index
    order = orders[order_index]
    try:
        if order.side is OrderSide.BUY:
            if state.open_position is not None:
                raise PortfolioExecutionError("Une position est déjà ouverte")
            if order.requested_cash is None or order.requested_cash <= ZERO:
                raise PortfolioExecutionError("Allocation d'entrée invalide")
            entry_calculation = calculate_entry_execution(
                execution_id=ids.next_execution(),
                order_id=order.id,
                timestamp=step.source_open_time,
                reference_price=step.open_price,
                allocated_cash=min(order.requested_cash, state.cash),
                cash_before=state.cash,
                fee_rate=config.fee_rate,
                slippage_rate=config.slippage_rate,
            )
            state.cash = entry_calculation.cash_after
            state.total_fees += entry_calculation.execution.fee
            executions.append(entry_calculation.execution)
            if order.observation_id is None:
                raise PortfolioInvariantError("Entrée sans observation source")
            state.open_position = open_long_position(
                position_id=ids.next_position(),
                symbol=symbol,
                quote_asset=config.quote_asset,
                observation_id=order.observation_id,
                execution=entry_calculation.execution,
                opened_bar_index=step_index,
            )
        else:
            position = state.open_position
            if position is None:
                raise PortfolioExecutionError("Aucune position à clôturer")
            exit_calculation = calculate_exit_execution(
                execution_id=ids.next_execution(),
                order_id=order.id,
                timestamp=step.source_open_time,
                reference_price=step.open_price,
                quantity=position.quantity,
                cash_before=state.cash,
                fee_rate=config.fee_rate,
                slippage_rate=config.slippage_rate,
            )
            executions.append(exit_calculation.execution)
            trade = close_long_position(
                trade_id=ids.next_trade(),
                position=position,
                exit_observation_id=order.observation_id,
                exit_calculation=exit_calculation,
                exit_reason=ExitReason.VALIDATION_LOST,
                duration_bars=step_index - position.opened_bar_index,
            )
            state.cash = exit_calculation.cash_after
            state.total_fees += exit_calculation.execution.fee
            state.realized_pnl += trade.realized_pnl
            state.completed_trades.append(trade)
            state.open_position = None
    except PortfolioExecutionError:
        orders[order_index] = replace(
            order,
            status=OrderStatus.REJECTED,
            rejection_reason=(
                OrderRejectionReason.INSUFFICIENT_CASH
                if order.side is OrderSide.BUY
                else OrderRejectionReason.NO_OPEN_POSITION
            ),
        )
    else:
        orders[order_index] = replace(order, status=OrderStatus.EXECUTED)
    finally:
        state.pending_order_index = None


def _equity_point(
    *,
    step: PortfolioSimulationStep,
    state: _MutablePortfolioState,
    running_peak: Decimal,
) -> tuple[EquityPoint, Decimal]:
    position_value, unrealized = value_open_position(state.open_position, step.close_price)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        equity = state.cash + position_value
    peak, drawdown = calculate_drawdown(equity=equity, running_peak=running_peak)
    return (
        EquityPoint(
            timestamp=step.decision_time,
            cash=state.cash,
            position_value=position_value,
            equity=equity,
            realized_pnl_cumulative=state.realized_pnl,
            unrealized_pnl=unrealized,
            fees_cumulative=state.total_fees,
            drawdown_ratio=drawdown,
            exposed=state.open_position is not None,
        ),
        peak,
    )


def _expire_pending_order(*, state: _MutablePortfolioState, orders: list[SimulatedOrder]) -> None:
    if state.pending_order_index is None:
        return
    index = state.pending_order_index
    orders[index] = replace(
        orders[index],
        status=OrderStatus.REJECTED,
        rejection_reason=OrderRejectionReason.END_OF_DATA,
    )
    state.pending_order_index = None


def _force_close(
    *,
    last_step: PortfolioSimulationStep,
    last_index: int,
    config: PortfolioSimulationConfig,
    state: _MutablePortfolioState,
    orders: list[SimulatedOrder],
    executions: list[SimulatedExecution],
    ids: _IdSequence,
) -> None:
    position = state.open_position
    if position is None:
        return
    order = SimulatedOrder(
        id=ids.next_order(),
        observation_id=None,
        side=OrderSide.SELL,
        intent_time=last_step.decision_time,
        execution_policy=ExecutionPolicy.NEXT_OPEN,
        requested_cash=None,
        status=OrderStatus.PENDING,
    )
    orders.append(order)
    calculation = calculate_exit_execution(
        execution_id=ids.next_execution(),
        order_id=order.id,
        timestamp=last_step.decision_time,
        reference_price=last_step.close_price,
        quantity=position.quantity,
        cash_before=state.cash,
        fee_rate=config.fee_rate,
        slippage_rate=config.slippage_rate,
    )
    executions.append(calculation.execution)
    trade = close_long_position(
        trade_id=ids.next_trade(),
        position=position,
        exit_observation_id=None,
        exit_calculation=calculation,
        exit_reason=ExitReason.END_OF_TEST,
        duration_bars=last_index - position.opened_bar_index + 1,
    )
    state.cash = calculation.cash_after
    state.total_fees += calculation.execution.fee
    state.realized_pnl += trade.realized_pnl
    state.completed_trades.append(trade)
    state.open_position = None
    orders[-1] = replace(order, status=OrderStatus.EXECUTED)


def simulate_portfolio(
    *,
    symbol: str,
    steps: Sequence[PortfolioSimulationStep],
    config: PortfolioSimulationConfig,
) -> PortfolioSimulationResult:
    """Exécute causalement une simulation mono-symbole entièrement pure."""
    _validate_inputs(symbol, steps)
    state = _MutablePortfolioState(
        cash=config.initial_capital,
        open_position=None,
        pending_order_index=None,
        realized_pnl=ZERO,
        total_fees=ZERO,
        completed_trades=[],
    )
    ids = _IdSequence()
    orders: list[SimulatedOrder] = []
    executions: list[SimulatedExecution] = []
    equity_curve: list[EquityPoint] = []
    previous_accepted = False
    running_peak = config.initial_capital
    exposed_closes = 0

    for index, step in enumerate(steps):
        _execute_pending(
            symbol=symbol,
            step=step,
            step_index=index,
            config=config,
            state=state,
            orders=orders,
            executions=executions,
            ids=ids,
        )
        intent = evaluate_accepted_state_transition(
            previous_accepted=previous_accepted,
            current_accepted=step.accepted,
            has_open_position=state.open_position is not None,
            pending_order_side=(
                orders[state.pending_order_index].side
                if state.pending_order_index is not None
                else None
            ),
        )
        if intent.action is StrategyAction.ENTER_LONG:
            _append_order(
                orders=orders,
                ids=ids,
                state=state,
                side=OrderSide.BUY,
                step=step,
                config=config,
            )
        elif intent.action is StrategyAction.EXIT_LONG:
            _append_order(
                orders=orders,
                ids=ids,
                state=state,
                side=OrderSide.SELL,
                step=step,
                config=config,
            )
        previous_accepted = step.accepted
        point, running_peak = _equity_point(
            step=step,
            state=state,
            running_peak=running_peak,
        )
        equity_curve.append(point)
        exposed_closes += int(point.exposed)
        _assert_invariants(state=state, orders=orders, executions=executions)

    _expire_pending_order(state=state, orders=orders)
    _force_close(
        last_step=steps[-1],
        last_index=len(steps) - 1,
        config=config,
        state=state,
        orders=orders,
        executions=executions,
        ids=ids,
    )
    final_point, _ = _equity_point(
        step=steps[-1],
        state=state,
        running_peak=running_peak,
    )
    equity_curve[-1] = final_point
    _assert_invariants(state=state, orders=orders, executions=executions)
    final_equity = final_point.equity
    metrics = calculate_portfolio_metrics(
        initial_capital=config.initial_capital,
        final_cash=state.cash,
        final_equity=final_equity,
        final_open_position=state.open_position,
        trades=state.completed_trades,
        equity_curve=equity_curve,
        total_fees=state.total_fees,
        exposed_closes=exposed_closes,
        total_closes=len(steps),
    )
    return PortfolioSimulationResult(
        version=1,
        quote_asset=config.quote_asset,
        config=config,
        orders=tuple(orders),
        executions=tuple(executions),
        trades=tuple(state.completed_trades),
        equity_curve=tuple(equity_curve),
        final_cash=state.cash,
        final_equity=final_equity,
        final_open_position=state.open_position,
        metrics=metrics,
    )
