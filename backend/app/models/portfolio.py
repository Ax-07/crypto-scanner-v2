"""Contrats publics additifs de simulation de portefeuille."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from app.domain.portfolio.decimal_utils import (
    HUNDRED,
    ONE,
    require_non_negative_decimal,
    require_positive_decimal,
)


def canonical_decimal(value: Decimal) -> str:
    """Sérialise un décimal fini sans exposant ni zéros finaux superflus."""
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


class PortfolioPositionSizingConfig(BaseModel):
    """Dimensionnement public v1, exprimé en pourcentage du cash."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["percent_cash"] = "percent_cash"
    value: Decimal = Decimal("100")

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: object) -> Decimal:
        percent = require_positive_decimal(value, name="position_sizing.value")  # type: ignore[arg-type]
        if percent > HUNDRED:
            raise ValueError("position_sizing.value doit être <= 100")
        return percent

    @field_serializer("value")
    def serialize_value(self, value: Decimal) -> str:
        return canonical_decimal(value)


class PortfolioSimulationConfigV1(BaseModel):
    """Configuration publique stricte du simulateur de portefeuille v1."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    quote_asset: str
    initial_capital: Decimal = Decimal("10000")
    position_sizing: PortfolioPositionSizingConfig = Field(
        default_factory=PortfolioPositionSizingConfig
    )
    execution_policy: Literal["next_open"] = "next_open"
    fee_rate: Decimal = Decimal("0.001")
    slippage_rate: Decimal = Decimal("0")
    end_of_test_policy: Literal["force_close"] = "force_close"

    @field_validator("quote_asset")
    @classmethod
    def normalize_quote_asset(cls, value: str) -> str:
        quote_asset = value.strip().upper()
        if not quote_asset:
            raise ValueError("quote_asset ne doit pas être vide")
        return quote_asset

    @field_validator("initial_capital", mode="before")
    @classmethod
    def validate_initial_capital(cls, value: object) -> Decimal:
        return require_positive_decimal(value, name="initial_capital")  # type: ignore[arg-type]

    @field_validator("fee_rate", "slippage_rate", mode="before")
    @classmethod
    def validate_rate(cls, value: object, info) -> Decimal:
        rate = require_non_negative_decimal(value, name=info.field_name)  # type: ignore[arg-type]
        if rate >= ONE:
            raise ValueError(f"{info.field_name} doit être < 1")
        return rate

    @field_serializer("initial_capital", "fee_rate", "slippage_rate")
    def serialize_decimal(self, value: Decimal) -> str:
        return canonical_decimal(value)


class PortfolioSimulationSummary(BaseModel):
    """Métriques publiques bornées, reprises sans recalcul du moteur."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    quote_asset: str
    initial_capital: Decimal
    final_cash: Decimal
    final_equity: Decimal
    net_profit: Decimal
    total_return_ratio: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal
    trade_count: int
    winning_trade_count: int
    losing_trade_count: int
    breakeven_trade_count: int
    win_rate: Decimal | None
    average_trade_return: Decimal | None
    max_drawdown_ratio: Decimal
    exposure_ratio: Decimal
    open_position_count: int

    @field_serializer(
        "initial_capital",
        "final_cash",
        "final_equity",
        "net_profit",
        "total_return_ratio",
        "realized_pnl",
        "unrealized_pnl",
        "total_fees",
        "win_rate",
        "average_trade_return",
        "max_drawdown_ratio",
        "exposure_ratio",
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return canonical_decimal(value) if value is not None else None


class PortfolioSimulationPublicResult(BaseModel):
    """Aperçu public additif; les détails restent internes au job."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    quote_asset: str
    summary: PortfolioSimulationSummary
    has_trades: bool
    has_equity_curve: bool
