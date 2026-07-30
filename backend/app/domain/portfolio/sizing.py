"""Dimensionnement pur des entrées de portefeuille."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app.domain.portfolio.decimal_utils import (
    DECIMAL_PRECISION,
    HUNDRED,
    ZERO,
    DecimalInput,
    PortfolioValidationError,
    require_non_negative_decimal,
    require_positive_decimal,
)


def calculate_percent_cash_allocation(
    *,
    available_cash: DecimalInput,
    position_size_percent: DecimalInput,
) -> Decimal:
    """Alloue un pourcentage du cash disponible, sans jamais le dépasser."""
    cash = require_non_negative_decimal(available_cash, name="available_cash")
    percent = require_positive_decimal(position_size_percent, name="position_size_percent")
    if percent > HUNDRED:
        raise PortfolioValidationError("position_size_percent doit être <= 100")
    if cash == ZERO:
        return ZERO
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        requested = cash * percent / HUNDRED
        return min(requested, cash)
