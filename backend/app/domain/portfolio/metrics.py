"""Calcul des métriques essentielles du portefeuille v1."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Sequence

from app.domain.portfolio.decimal_utils import DECIMAL_PRECISION, ZERO, decimal_sum
from app.domain.portfolio.types import (
    EquityPoint,
    PortfolioMetrics,
    SimulatedPosition,
    SimulatedTrade,
)


def calculate_drawdown(*, equity: Decimal, running_peak: Decimal) -> tuple[Decimal, Decimal]:
    """Retourne le nouveau sommet et un drawdown positif peak-to-trough."""
    peak = max(equity, running_peak)
    if peak <= ZERO:
        return peak, ZERO
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return peak, (peak - equity) / peak


def calculate_portfolio_metrics(
    *,
    initial_capital: Decimal,
    final_cash: Decimal,
    final_equity: Decimal,
    final_open_position: SimulatedPosition | None,
    trades: Sequence[SimulatedTrade],
    equity_curve: Sequence[EquityPoint],
    total_fees: Decimal,
    exposed_closes: int,
    total_closes: int,
) -> PortfolioMetrics:
    """Agrège les métriques sans produire de NaN ni d'infini."""
    realized = decimal_sum([trade.realized_pnl for trade in trades])
    unrealized = (
        equity_curve[-1].unrealized_pnl
        if equity_curve and final_open_position is not None
        else ZERO
    )
    wins = sum(trade.realized_pnl > ZERO for trade in trades)
    losses = sum(trade.realized_pnl < ZERO for trade in trades)
    breakeven = len(trades) - wins - losses
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        net_profit = final_equity - initial_capital
        total_return = net_profit / initial_capital
        win_rate = Decimal(wins) / Decimal(len(trades)) if trades else None
        average_return = (
            decimal_sum([trade.return_ratio for trade in trades]) / Decimal(len(trades))
            if trades
            else None
        )
        exposure = Decimal(exposed_closes) / Decimal(total_closes)
    return PortfolioMetrics(
        initial_capital=initial_capital,
        final_cash=final_cash,
        final_equity=final_equity,
        net_profit=net_profit,
        total_return_ratio=total_return,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_fees=total_fees,
        trade_count=len(trades),
        winning_trade_count=wins,
        losing_trade_count=losses,
        breakeven_trade_count=breakeven,
        win_rate=win_rate,
        average_trade_return=average_return,
        max_drawdown_ratio=max((point.drawdown_ratio for point in equity_curve), default=ZERO),
        exposure_ratio=exposure,
        open_position_count=int(final_open_position is not None),
    )
