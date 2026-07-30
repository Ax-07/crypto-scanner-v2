"""Types internes immuables du simulateur de portefeuille v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from app.domain.portfolio.decimal_utils import (
    HUNDRED,
    ONE,
    ZERO,
    PortfolioValidationError,
    require_non_negative_decimal,
    require_positive_decimal,
    to_finite_decimal,
)


class PositionSizingMode(str, Enum):
    """Modes de dimensionnement pris en charge."""

    PERCENT_CASH = "percent_cash"


class ExecutionPolicy(str, Enum):
    """Politiques d'exécution prises en charge."""

    NEXT_OPEN = "next_open"


class EndOfTestPolicy(str, Enum):
    """Politiques de fin de simulation prises en charge."""

    FORCE_CLOSE = "force_close"


class OrderSide(str, Enum):
    """Côté d'un ordre spot long-only."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """État final ou transitoire d'un ordre simulé."""

    PENDING = "pending"
    EXECUTED = "executed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PositionStatus(str, Enum):
    """État d'une position simulée."""

    OPEN = "open"
    CLOSED = "closed"


class StrategyAction(str, Enum):
    """Actions produites par la stratégie v1."""

    ENTER_LONG = "enter_long"
    EXIT_LONG = "exit_long"
    HOLD = "hold"


class StrategyReason(str, Enum):
    """Motif d'une décision de stratégie."""

    VALIDATION_GAINED = "validation_gained"
    VALIDATION_LOST = "validation_lost"
    VALIDATION_UNCHANGED = "validation_unchanged"
    POSITION_ALREADY_OPEN = "position_already_open"
    ORDER_ALREADY_PENDING = "order_already_pending"


class OrderRejectionReason(str, Enum):
    """Raisons opérationnelles strictes de rejet d'ordre."""

    INSUFFICIENT_CASH = "insufficient_cash"
    INVALID_REFERENCE_PRICE = "invalid_reference_price"
    INVALID_EXECUTION_PRICE = "invalid_execution_price"
    MISSING_EXECUTION_CANDLE = "missing_execution_candle"
    POSITION_ALREADY_OPEN = "position_already_open"
    NO_OPEN_POSITION = "no_open_position"
    ENTRY_ORDER_ALREADY_PENDING = "entry_order_already_pending"
    EXIT_ORDER_ALREADY_PENDING = "exit_order_already_pending"
    BELOW_INTERNAL_MINIMUM = "below_internal_minimum"
    END_OF_DATA = "end_of_data"
    INVALID_QUANTITY = "invalid_quantity"


class ExitReason(str, Enum):
    """Raisons de clôture d'un trade v1."""

    VALIDATION_LOST = "validation_lost"
    END_OF_TEST = "end_of_test"


def _enum_value(enum_type: type[Enum], value: object, *, name: str) -> Enum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise PortfolioValidationError(f"{name} non pris en charge: {value!r}") from exc


def _require_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PortfolioValidationError(f"{name} ne doit pas être vide")
    return value.strip()


def _require_datetime(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise PortfolioValidationError(f"{name} doit être un datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise PortfolioValidationError(f"{name} doit être timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class PortfolioSimulationConfig:
    """Configuration interne et fermée du moteur v1."""

    quote_asset: str
    version: Literal[1] = 1
    initial_capital: Decimal = Decimal("10000")
    position_sizing_mode: PositionSizingMode = PositionSizingMode.PERCENT_CASH
    position_size_percent: Decimal = HUNDRED
    execution_policy: ExecutionPolicy = ExecutionPolicy.NEXT_OPEN
    fee_rate: Decimal = Decimal("0.001")
    slippage_rate: Decimal = Decimal("0")
    end_of_test_policy: EndOfTestPolicy = EndOfTestPolicy.FORCE_CLOSE

    def __post_init__(self) -> None:
        if self.version != 1:
            raise PortfolioValidationError("version doit valoir 1")
        object.__setattr__(self, "quote_asset", _require_text(self.quote_asset, name="quote_asset"))
        capital = require_positive_decimal(self.initial_capital, name="initial_capital")
        percent = require_positive_decimal(self.position_size_percent, name="position_size_percent")
        fee = require_non_negative_decimal(self.fee_rate, name="fee_rate")
        slippage = require_non_negative_decimal(self.slippage_rate, name="slippage_rate")
        if percent > HUNDRED:
            raise PortfolioValidationError("position_size_percent doit être <= 100")
        if fee >= ONE:
            raise PortfolioValidationError("fee_rate doit être < 1")
        if slippage >= ONE:
            raise PortfolioValidationError("slippage_rate doit être < 1")
        object.__setattr__(self, "initial_capital", capital)
        object.__setattr__(self, "position_size_percent", percent)
        object.__setattr__(self, "fee_rate", fee)
        object.__setattr__(self, "slippage_rate", slippage)
        object.__setattr__(
            self,
            "position_sizing_mode",
            _enum_value(
                PositionSizingMode,
                self.position_sizing_mode,
                name="position_sizing_mode",
            ),
        )
        object.__setattr__(
            self,
            "execution_policy",
            _enum_value(ExecutionPolicy, self.execution_policy, name="execution_policy"),
        )
        object.__setattr__(
            self,
            "end_of_test_policy",
            _enum_value(
                EndOfTestPolicy,
                self.end_of_test_policy,
                name="end_of_test_policy",
            ),
        )


@dataclass(frozen=True, slots=True)
class PortfolioSimulationStep:
    """Bougie primaire minimale et décision déjà calculée."""

    observation_id: str
    source_open_time: datetime
    decision_time: datetime
    open_price: Decimal
    close_price: Decimal
    accepted: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observation_id", _require_text(self.observation_id, name="observation_id")
        )
        opened = _require_datetime(self.source_open_time, name="source_open_time")
        decided = _require_datetime(self.decision_time, name="decision_time")
        if opened >= decided:
            raise PortfolioValidationError("source_open_time doit précéder decision_time")
        if not isinstance(self.accepted, bool):
            raise PortfolioValidationError("accepted doit être booléen")
        object.__setattr__(
            self, "open_price", require_positive_decimal(self.open_price, name="open_price")
        )
        object.__setattr__(
            self, "close_price", require_positive_decimal(self.close_price, name="close_price")
        )

    @property
    def timestamp(self) -> datetime:
        """Alias explicite de l'instant de décision à la clôture."""
        return self.decision_time


@dataclass(frozen=True, slots=True)
class StrategyIntent:
    """Décision pure de la stratégie, avant validation opérationnelle."""

    action: StrategyAction
    reason: StrategyReason


@dataclass(frozen=True, slots=True)
class SimulatedOrder:
    """Ordre simulé traçable vers l'observation qui l'a créé."""

    id: str
    observation_id: str | None
    side: OrderSide
    intent_time: datetime
    execution_policy: ExecutionPolicy
    requested_cash: Decimal | None
    status: OrderStatus
    rejection_reason: OrderRejectionReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_text(self.id, name="order.id"))
        if self.observation_id is not None:
            object.__setattr__(
                self,
                "observation_id",
                _require_text(self.observation_id, name="order.observation_id"),
            )
        _require_datetime(self.intent_time, name="order.intent_time")
        object.__setattr__(self, "side", _enum_value(OrderSide, self.side, name="order.side"))
        object.__setattr__(
            self,
            "execution_policy",
            _enum_value(ExecutionPolicy, self.execution_policy, name="order.execution_policy"),
        )
        object.__setattr__(
            self, "status", _enum_value(OrderStatus, self.status, name="order.status")
        )
        if self.requested_cash is not None:
            object.__setattr__(
                self,
                "requested_cash",
                require_non_negative_decimal(self.requested_cash, name="order.requested_cash"),
            )
        if self.rejection_reason is not None:
            object.__setattr__(
                self,
                "rejection_reason",
                _enum_value(
                    OrderRejectionReason,
                    self.rejection_reason,
                    name="order.rejection_reason",
                ),
            )
        if self.status is OrderStatus.REJECTED and self.rejection_reason is None:
            raise PortfolioValidationError("Un ordre rejeté exige une raison")
        if self.status is not OrderStatus.REJECTED and self.rejection_reason is not None:
            raise PortfolioValidationError("Seul un ordre rejeté porte une raison")


@dataclass(frozen=True, slots=True)
class SimulatedExecution:
    """Remplissage déterministe d'un ordre simulé."""

    id: str
    order_id: str
    timestamp: datetime
    side: OrderSide
    reference_price: Decimal
    execution_price: Decimal
    quantity: Decimal
    gross_notional: Decimal
    fee: Decimal
    slippage_rate: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_text(self.id, name="execution.id"))
        object.__setattr__(
            self, "order_id", _require_text(self.order_id, name="execution.order_id")
        )
        _require_datetime(self.timestamp, name="execution.timestamp")
        object.__setattr__(self, "side", _enum_value(OrderSide, self.side, name="execution.side"))
        for name in (
            "reference_price",
            "execution_price",
            "quantity",
            "gross_notional",
        ):
            object.__setattr__(
                self,
                name,
                require_positive_decimal(getattr(self, name), name=f"execution.{name}"),
            )
        object.__setattr__(
            self,
            "fee",
            require_non_negative_decimal(self.fee, name="execution.fee"),
        )
        slippage = require_non_negative_decimal(self.slippage_rate, name="execution.slippage_rate")
        if slippage >= ONE:
            raise PortfolioValidationError("execution.slippage_rate doit être < 1")
        object.__setattr__(self, "slippage_rate", slippage)


@dataclass(frozen=True, slots=True)
class SimulatedPosition:
    """Position longue ouverte, sans sortie fictive."""

    id: str
    symbol: str
    quote_asset: str
    opened_at: datetime
    entry_observation_id: str
    entry_order_id: str
    entry_execution_id: str
    quantity: Decimal
    entry_execution_price: Decimal
    entry_notional: Decimal
    entry_fee: Decimal
    total_entry_cost: Decimal
    opened_bar_index: int
    status: PositionStatus = PositionStatus.OPEN

    def __post_init__(self) -> None:
        for name in (
            "id",
            "symbol",
            "quote_asset",
            "entry_observation_id",
            "entry_order_id",
            "entry_execution_id",
        ):
            object.__setattr__(
                self, name, _require_text(getattr(self, name), name=f"position.{name}")
            )
        _require_datetime(self.opened_at, name="position.opened_at")
        for name in (
            "quantity",
            "entry_execution_price",
            "entry_notional",
            "total_entry_cost",
        ):
            object.__setattr__(
                self,
                name,
                require_positive_decimal(getattr(self, name), name=f"position.{name}"),
            )
        object.__setattr__(
            self,
            "entry_fee",
            require_non_negative_decimal(self.entry_fee, name="position.entry_fee"),
        )
        if self.opened_bar_index < 0:
            raise PortfolioValidationError("position.opened_bar_index doit être positif")
        object.__setattr__(
            self,
            "status",
            _enum_value(PositionStatus, self.status, name="position.status"),
        )


@dataclass(frozen=True, slots=True)
class SimulatedTrade:
    """Cycle économique long entièrement clôturé."""

    id: str
    position_id: str
    symbol: str
    quote_asset: str
    entry_observation_id: str
    exit_observation_id: str | None
    entry_order_id: str
    exit_order_id: str
    entry_execution_id: str
    exit_execution_id: str
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
    duration_bars: int
    exit_reason: ExitReason

    def __post_init__(self) -> None:
        for name in (
            "id",
            "position_id",
            "symbol",
            "quote_asset",
            "entry_observation_id",
            "entry_order_id",
            "exit_order_id",
            "entry_execution_id",
            "exit_execution_id",
        ):
            object.__setattr__(self, name, _require_text(getattr(self, name), name=f"trade.{name}"))
        if self.exit_observation_id is not None:
            object.__setattr__(
                self,
                "exit_observation_id",
                _require_text(self.exit_observation_id, name="trade.exit_observation_id"),
            )
        _require_datetime(self.entry_time, name="trade.entry_time")
        _require_datetime(self.exit_time, name="trade.exit_time")
        if self.exit_time < self.entry_time:
            raise PortfolioValidationError("trade.exit_time précède trade.entry_time")
        for name in (
            "entry_price",
            "exit_price",
            "quantity",
            "gross_exit_proceeds",
            "net_exit_proceeds",
        ):
            object.__setattr__(
                self,
                name,
                require_positive_decimal(getattr(self, name), name=f"trade.{name}"),
            )
        for name in ("entry_fee", "exit_fee"):
            object.__setattr__(
                self,
                name,
                require_non_negative_decimal(getattr(self, name), name=f"trade.{name}"),
            )
        for name in ("realized_pnl", "return_ratio"):
            object.__setattr__(
                self,
                name,
                to_finite_decimal(getattr(self, name), name=f"trade.{name}"),
            )
        if self.duration_bars < 0:
            raise PortfolioValidationError("trade.duration_bars doit être positif")
        object.__setattr__(
            self,
            "exit_reason",
            _enum_value(ExitReason, self.exit_reason, name="trade.exit_reason"),
        )


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Valorisation comptable à une clôture primaire."""

    timestamp: datetime
    cash: Decimal
    position_value: Decimal
    equity: Decimal
    realized_pnl_cumulative: Decimal
    unrealized_pnl: Decimal
    fees_cumulative: Decimal
    drawdown_ratio: Decimal
    exposed: bool

    def __post_init__(self) -> None:
        _require_datetime(self.timestamp, name="equity.timestamp")
        for name in (
            "cash",
            "position_value",
            "equity",
            "fees_cumulative",
            "drawdown_ratio",
        ):
            object.__setattr__(
                self,
                name,
                require_non_negative_decimal(getattr(self, name), name=f"equity.{name}"),
            )
        for name in ("realized_pnl_cumulative", "unrealized_pnl"):
            object.__setattr__(
                self,
                name,
                to_finite_decimal(getattr(self, name), name=f"equity.{name}"),
            )
        if self.drawdown_ratio > ONE:
            raise PortfolioValidationError("equity.drawdown_ratio doit être <= 1")


@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    """Métriques essentielles internes du MVP."""

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


@dataclass(frozen=True, slots=True)
class PortfolioSimulationResult:
    """Résultat interne complet et immuable du moteur pur."""

    version: Literal[1]
    quote_asset: str
    config: PortfolioSimulationConfig
    orders: tuple[SimulatedOrder, ...]
    executions: tuple[SimulatedExecution, ...]
    trades: tuple[SimulatedTrade, ...]
    equity_curve: tuple[EquityPoint, ...]
    final_cash: Decimal
    final_equity: Decimal
    final_open_position: SimulatedPosition | None
    metrics: PortfolioMetrics


def validate_accounting_value(value: Decimal, *, name: str, positive: bool = False) -> None:
    """Valide une valeur déjà calculée dans les modèles comptables."""
    checked = to_finite_decimal(value, name=name)
    if positive and checked <= ZERO:
        raise PortfolioValidationError(f"{name} doit être strictement positif")
