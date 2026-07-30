"""Contrats publics additifs de simulation de portefeuille."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
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
    canonical_decimal,
    require_non_negative_decimal,
    require_positive_decimal,
)


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


class PortfolioDetailsStatus(StrEnum):
    """Disponibilité durable des détails d'une simulation."""

    COMPLETE = "complete"
    UNAVAILABLE_LEGACY = "unavailable_legacy"


class PortfolioTradeV1(BaseModel):
    """Trade fermé public, sans duplication des ordres et exécutions."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    sequence: int = Field(ge=0)
    trade_id: str
    position_id: str
    symbol: str
    quote_asset: str
    entry_observation_id: str
    exit_observation_id: str | None
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    gross_exit_proceeds: Decimal
    net_exit_proceeds: Decimal
    realized_pnl: Decimal
    return_ratio: Decimal
    duration_bars: int = Field(ge=0)
    exit_reason: Literal["validation_lost", "end_of_test"]

    @field_serializer(
        "entry_price",
        "exit_price",
        "quantity",
        "entry_fee",
        "exit_fee",
        "gross_exit_proceeds",
        "net_exit_proceeds",
        "realized_pnl",
        "return_ratio",
    )
    def serialize_trade_decimal(self, value: Decimal) -> str:
        return canonical_decimal(value)


class PortfolioEquityPointV1(BaseModel):
    """Point public exact de la courbe d'equity persistée."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    sequence: int = Field(ge=0)
    timestamp: datetime
    cash: Decimal
    position_value: Decimal
    equity: Decimal
    realized_pnl_cumulative: Decimal
    unrealized_pnl: Decimal
    fees_cumulative: Decimal
    drawdown_ratio: Decimal

    @field_serializer(
        "cash",
        "position_value",
        "equity",
        "realized_pnl_cumulative",
        "unrealized_pnl",
        "fees_cumulative",
        "drawdown_ratio",
    )
    def serialize_equity_decimal(self, value: Decimal) -> str:
        return canonical_decimal(value)


class PortfolioTradePage(BaseModel):
    """Page SQL stable de trades."""

    model_config = ConfigDict(extra="forbid")

    items: list[PortfolioTradeV1]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool


class PortfolioEquityPage(BaseModel):
    """Page brute ou sélection déterministe de points existants."""

    model_config = ConfigDict(extra="forbid")

    items: list[PortfolioEquityPointV1]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool
    sampled: bool
    source_point_count: int = Field(ge=0)


class PortfolioRunMetadataV1(BaseModel):
    """Métadonnées publiques bornées d'un run durable."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    schema_version: Literal[1] = 1
    engine_version: str
    quote_asset: str
    summary: PortfolioSimulationSummary
    details_status: PortfolioDetailsStatus
    order_count: int = Field(ge=0)
    execution_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    equity_point_count: int = Field(ge=0)
    available_after_restart: bool
