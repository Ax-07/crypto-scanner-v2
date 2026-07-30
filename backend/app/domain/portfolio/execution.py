"""Calcul pur des exécutions d'entrée et de sortie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from app.domain.portfolio.decimal_utils import (
    DECIMAL_PRECISION,
    ONE,
    ZERO,
    DecimalInput,
    PortfolioExecutionError,
    normalize_cash,
    require_non_negative_decimal,
    require_positive_decimal,
)
from app.domain.portfolio.types import OrderSide, SimulatedExecution


@dataclass(frozen=True, slots=True)
class EntryExecutionCalculation:
    """Résultat comptable d'une exécution d'entrée."""

    execution: SimulatedExecution
    cash_after: Decimal


@dataclass(frozen=True, slots=True)
class ExitExecutionCalculation:
    """Résultat comptable d'une exécution de sortie."""

    execution: SimulatedExecution
    net_proceeds: Decimal
    cash_after: Decimal


def calculate_entry_execution(
    *,
    execution_id: str,
    order_id: str,
    timestamp: datetime,
    reference_price: DecimalInput,
    allocated_cash: DecimalInput,
    cash_before: DecimalInput,
    fee_rate: DecimalInput,
    slippage_rate: DecimalInput,
) -> EntryExecutionCalculation:
    """Calcule un achat long avec allocation incluant les frais."""
    reference = require_positive_decimal(reference_price, name="reference_price")
    allocation = require_positive_decimal(allocated_cash, name="allocated_cash")
    cash = require_non_negative_decimal(cash_before, name="cash_before")
    fee = require_non_negative_decimal(fee_rate, name="fee_rate")
    slippage = require_non_negative_decimal(slippage_rate, name="slippage_rate")
    if allocation > cash:
        raise PortfolioExecutionError("allocated_cash dépasse le cash disponible")
    if fee >= ONE or slippage >= ONE:
        raise PortfolioExecutionError("Les taux d'exécution doivent être < 1")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        execution_price = reference * (ONE + slippage)
        if execution_price <= ZERO or not execution_price.is_finite():
            raise PortfolioExecutionError("Prix d'exécution d'entrée invalide")
        notional = allocation / (ONE + fee)
        entry_fee = notional * fee
        quantity = notional / execution_price
        if quantity <= ZERO or not quantity.is_finite():
            raise PortfolioExecutionError("Quantité d'entrée invalide")
        cash_after = normalize_cash(cash - notional - entry_fee)
    execution = SimulatedExecution(
        id=execution_id,
        order_id=order_id,
        timestamp=timestamp,
        side=OrderSide.BUY,
        reference_price=reference,
        execution_price=execution_price,
        quantity=quantity,
        gross_notional=notional,
        fee=entry_fee,
        slippage_rate=slippage,
    )
    return EntryExecutionCalculation(execution=execution, cash_after=cash_after)


def calculate_exit_execution(
    *,
    execution_id: str,
    order_id: str,
    timestamp: datetime,
    reference_price: DecimalInput,
    quantity: DecimalInput,
    cash_before: DecimalInput,
    fee_rate: DecimalInput,
    slippage_rate: DecimalInput,
) -> ExitExecutionCalculation:
    """Calcule la vente totale d'une position longue."""
    reference = require_positive_decimal(reference_price, name="reference_price")
    position_quantity = require_positive_decimal(quantity, name="quantity")
    cash = require_non_negative_decimal(cash_before, name="cash_before")
    fee = require_non_negative_decimal(fee_rate, name="fee_rate")
    slippage = require_non_negative_decimal(slippage_rate, name="slippage_rate")
    if fee >= ONE or slippage >= ONE:
        raise PortfolioExecutionError("Les taux d'exécution doivent être < 1")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        execution_price = reference * (ONE - slippage)
        if execution_price <= ZERO or not execution_price.is_finite():
            raise PortfolioExecutionError("Prix d'exécution de sortie invalide")
        gross_proceeds = position_quantity * execution_price
        exit_fee = gross_proceeds * fee
        net_proceeds = gross_proceeds - exit_fee
        cash_after = normalize_cash(cash + net_proceeds)
    execution = SimulatedExecution(
        id=execution_id,
        order_id=order_id,
        timestamp=timestamp,
        side=OrderSide.SELL,
        reference_price=reference,
        execution_price=execution_price,
        quantity=position_quantity,
        gross_notional=gross_proceeds,
        fee=exit_fee,
        slippage_rate=slippage,
    )
    return ExitExecutionCalculation(
        execution=execution,
        net_proceeds=net_proceeds,
        cash_after=cash_after,
    )
