"""Contrats publics additifs de simulation de portefeuille."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    WithJsonSchema,
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

PUBLIC_DECIMAL_SCHEMA = {
    "type": "string",
    "pattern": r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$",
}
PublicDecimalInput = Annotated[
    Decimal,
    WithJsonSchema(PUBLIC_DECIMAL_SCHEMA, mode="validation"),
]


def _require_public_decimal_string(value: object, *, name: str) -> object:
    if not isinstance(value, str):
        raise ValueError(f"{name} doit être une chaîne décimale")
    return value


class PortfolioPositionSizingConfig(BaseModel):
    """Dimensionnement public v1, exprimé en pourcentage du cash."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["percent_cash"] = "percent_cash"
    value: PublicDecimalInput = Decimal("100")

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: object) -> Decimal:
        value = _require_public_decimal_string(value, name="position_sizing.value")
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
    initial_capital: PublicDecimalInput = Decimal("10000")
    position_sizing: PortfolioPositionSizingConfig = Field(
        default_factory=PortfolioPositionSizingConfig
    )
    execution_policy: Literal["next_open"] = "next_open"
    fee_rate: PublicDecimalInput = Decimal("0.001")
    slippage_rate: PublicDecimalInput = Decimal("0")
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
        value = _require_public_decimal_string(value, name="initial_capital")
        return require_positive_decimal(value, name="initial_capital")  # type: ignore[arg-type]

    @field_validator("fee_rate", "slippage_rate", mode="before")
    @classmethod
    def validate_rate(cls, value: object, info) -> Decimal:
        value = _require_public_decimal_string(value, name=info.field_name)
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
    quote_asset: str = Field(min_length=1)
    initial_capital: Decimal = Field(gt=0)
    final_cash: Decimal = Field(ge=0)
    final_equity: Decimal = Field(ge=0)
    net_profit: Decimal
    total_return_ratio: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal = Field(ge=0)
    trade_count: int = Field(ge=0)
    winning_trade_count: int = Field(ge=0)
    losing_trade_count: int = Field(ge=0)
    breakeven_trade_count: int = Field(ge=0)
    win_rate: Decimal | None = Field(ge=0, le=1)
    average_trade_return: Decimal | None
    max_drawdown_ratio: Decimal = Field(ge=0, le=1)
    exposure_ratio: Decimal = Field(ge=0, le=1)
    open_position_count: int = Field(ge=0, le=1)

    @field_serializer(
        "initial_capital",
        "final_cash",
        "final_equity",
        "net_profit",
        "total_return_ratio",
        "realized_pnl",
        "unrealized_pnl",
        "total_fees",
        "max_drawdown_ratio",
        "exposure_ratio",
    )
    def serialize_decimal(self, value: Decimal) -> str:
        return canonical_decimal(value)

    @field_serializer("win_rate", "average_trade_return")
    def serialize_optional_decimal(self, value: Decimal | None) -> str | None:
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
    trade_id: str = Field(min_length=1)
    position_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    quote_asset: str = Field(min_length=1)
    entry_observation_id: str = Field(min_length=1)
    exit_observation_id: str | None = Field(min_length=1)
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal = Field(gt=0)
    exit_price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    entry_fee: Decimal = Field(ge=0)
    exit_fee: Decimal = Field(ge=0)
    gross_exit_proceeds: Decimal = Field(ge=0)
    net_exit_proceeds: Decimal = Field(ge=0)
    realized_pnl: Decimal
    return_ratio: Decimal
    duration_bars: int = Field(ge=0)
    exit_reason: Literal["validation_lost", "end_of_test"]

    @field_validator("entry_time", "exit_time")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("un timestamp UTC avec fuseau est requis")
        return value

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
    cash: Decimal = Field(ge=0)
    position_value: Decimal = Field(ge=0)
    equity: Decimal = Field(ge=0)
    realized_pnl_cumulative: Decimal
    unrealized_pnl: Decimal
    fees_cumulative: Decimal = Field(ge=0)
    drawdown_ratio: Decimal = Field(ge=0, le=1)

    @field_validator("timestamp")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("un timestamp UTC avec fuseau est requis")
        return value

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
    limit: int = Field(ge=1, le=500)
    has_more: bool


class PortfolioEquityPage(BaseModel):
    """Page brute ou sélection déterministe de points existants."""

    model_config = ConfigDict(extra="forbid")

    items: list[PortfolioEquityPointV1]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=2_000)
    has_more: bool
    sampled: bool
    source_point_count: int = Field(ge=0)


class PortfolioRunMetadataV1(BaseModel):
    """Métadonnées publiques bornées d'un run durable."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    schema_version: Literal[1] = 1
    engine_version: str = Field(min_length=1)
    quote_asset: str = Field(min_length=1)
    summary: PortfolioSimulationSummary
    details_status: PortfolioDetailsStatus
    order_count: int = Field(ge=0)
    execution_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    equity_point_count: int = Field(ge=0)
    available_after_restart: bool
