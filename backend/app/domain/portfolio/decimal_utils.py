"""Conversions et validations décimales du simulateur de portefeuille."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import TypeAlias

DecimalInput: TypeAlias = Decimal | str | int | float
DECIMAL_PRECISION = 28
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
CASH_TOLERANCE = Decimal("1e-12")


class PortfolioDomainError(ValueError):
    """Erreur explicite du domaine de simulation de portefeuille."""


class PortfolioValidationError(PortfolioDomainError):
    """Entrée ou configuration invalide."""


class PortfolioExecutionError(PortfolioDomainError):
    """Calcul d'exécution impossible."""


class PortfolioInvariantError(PortfolioDomainError):
    """Invariant comptable interne violé."""


def canonical_decimal(value: DecimalInput, *, name: str = "value") -> str:
    """Retourne la forme texte canonique d'un décimal fini."""
    decimal_value = to_finite_decimal(value, name=name)
    normalized = decimal_value.normalize()
    if normalized == ZERO:
        return "0"
    return format(normalized, "f")


def to_finite_decimal(value: DecimalInput, *, name: str) -> Decimal:
    """Convertit via la représentation textuelle et exige une valeur finie."""
    if isinstance(value, bool):
        raise PortfolioValidationError(f"{name} doit être un nombre décimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PortfolioValidationError(f"{name} doit être un nombre décimal valide") from exc
    if not result.is_finite():
        raise PortfolioValidationError(f"{name} doit être fini")
    return result


def require_positive_decimal(value: DecimalInput, *, name: str) -> Decimal:
    """Exige une valeur décimale finie strictement positive."""
    result = to_finite_decimal(value, name=name)
    if result <= ZERO:
        raise PortfolioValidationError(f"{name} doit être strictement positif")
    return result


def require_non_negative_decimal(value: DecimalInput, *, name: str) -> Decimal:
    """Exige une valeur décimale finie positive ou nulle."""
    result = to_finite_decimal(value, name=name)
    if result < ZERO:
        raise PortfolioValidationError(f"{name} doit être positif ou nul")
    return result


def normalize_cash(value: DecimalInput) -> Decimal:
    """Ramène à zéro une dérive négative inférieure à la tolérance documentée."""
    cash = to_finite_decimal(value, name="cash")
    if cash < ZERO:
        if abs(cash) <= CASH_TOLERANCE:
            return ZERO
        raise PortfolioInvariantError("Le cash ne peut pas être négatif")
    return cash


def decimal_sum(values: tuple[Decimal, ...] | list[Decimal]) -> Decimal:
    """Additionne avec le contexte déterministe du moteur."""
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return sum(values, ZERO)
