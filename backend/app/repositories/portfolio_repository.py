"""Persistance SQLite atomique des détails de portefeuille v1."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

import aiosqlite

from app.database.connection import Database
from app.domain.portfolio import (
    EndOfTestPolicy,
    EquityPoint,
    ExecutionPolicy,
    ExitReason,
    OrderRejectionReason,
    OrderSide,
    OrderStatus,
    PortfolioMetrics,
    PortfolioSimulationConfig,
    PortfolioSimulationResult,
    PositionSizingMode,
    PositionStatus,
    SimulatedExecution,
    SimulatedOrder,
    SimulatedPosition,
    SimulatedTrade,
)
from app.domain.portfolio.decimal_utils import canonical_decimal, to_finite_decimal

PORTFOLIO_SCHEMA_VERSION = 1
PORTFOLIO_ENGINE_VERSION = "portfolio-simulation-v1"
PORTFOLIO_WRITE_BATCH_SIZE = 1_000
PORTFOLIO_READ_BATCH_SIZE = 1_000
PORTFOLIO_SAMPLE_MAX_POINTS = 2_000


class PortfolioPersistenceError(RuntimeError):
    """Erreur durable contrôlée, sans détail SQLite destiné au client."""


@dataclass(frozen=True, slots=True)
class StoredPortfolioRun:
    """Métadonnées et état borné nécessaires à une reconstruction exacte."""

    job_id: str
    schema_version: int
    engine_version: str
    config_fingerprint: str
    quote_asset: str
    config: PortfolioSimulationConfig
    metrics: PortfolioMetrics
    final_cash: Decimal
    final_equity: Decimal
    final_open_position: SimulatedPosition | None
    order_count: int
    execution_count: int
    trade_count: int
    equity_point_count: int
    created_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class StoredTrade:
    """Trade accompagné de sa séquence canonique."""

    sequence: int
    trade: SimulatedTrade


@dataclass(frozen=True, slots=True)
class StoredEquityPoint:
    """Point d'equity accompagné de sa séquence canonique."""

    sequence: int
    point: EquityPoint


@dataclass(frozen=True, slots=True)
class StoredTradePage:
    items: tuple[StoredTrade, ...]
    total: int


@dataclass(frozen=True, slots=True)
class StoredEquityPage:
    items: tuple[StoredEquityPoint, ...]
    total: int


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PortfolioPersistenceError("portfolio_persistence_failed")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortfolioPersistenceError("portfolio_persistence_failed")
    return parsed.astimezone(timezone.utc)


def _decimal(value: str, *, name: str) -> Decimal:
    return to_finite_decimal(value, name=name)


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Type non sérialisable: {type(value).__name__}")


def _json(value: object) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _config_from_json(payload: str) -> PortfolioSimulationConfig:
    item = json.loads(payload)
    return PortfolioSimulationConfig(
        version=item["version"],
        quote_asset=item["quote_asset"],
        initial_capital=_decimal(item["initial_capital"], name="initial_capital"),
        position_sizing_mode=PositionSizingMode(item["position_sizing_mode"]),
        position_size_percent=_decimal(item["position_size_percent"], name="position_size_percent"),
        execution_policy=ExecutionPolicy(item["execution_policy"]),
        fee_rate=_decimal(item["fee_rate"], name="fee_rate"),
        slippage_rate=_decimal(item["slippage_rate"], name="slippage_rate"),
        end_of_test_policy=EndOfTestPolicy(item["end_of_test_policy"]),
    )


def _metrics_from_json(payload: str) -> PortfolioMetrics:
    item = json.loads(payload)
    decimal_fields = {
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
    }
    nullable_decimal_fields = {"win_rate", "average_trade_return"}
    for name in decimal_fields:
        item[name] = _decimal(item[name], name=f"metrics.{name}")
    for name in nullable_decimal_fields:
        if item[name] is not None:
            item[name] = _decimal(item[name], name=f"metrics.{name}")
    return PortfolioMetrics(**item)


def _position_from_json(payload: str | None) -> SimulatedPosition | None:
    if payload is None:
        return None
    item = json.loads(payload)
    for name in (
        "quantity",
        "entry_execution_price",
        "entry_notional",
        "entry_fee",
        "total_entry_cost",
    ):
        item[name] = _decimal(item[name], name=f"position.{name}")
    item["opened_at"] = _datetime(item["opened_at"])
    item["status"] = PositionStatus(item["status"])
    return SimulatedPosition(**item)


def _order(row: aiosqlite.Row) -> SimulatedOrder:
    return SimulatedOrder(
        id=row["order_id"],
        observation_id=row["observation_id"],
        side=OrderSide(row["side"]),
        intent_time=_datetime(row["intent_time"]),
        execution_policy=ExecutionPolicy(row["execution_policy"]),
        requested_cash=(
            _decimal(row["requested_cash"], name="order.requested_cash")
            if row["requested_cash"] is not None
            else None
        ),
        status=OrderStatus(row["status"]),
        rejection_reason=(
            OrderRejectionReason(row["rejection_reason"])
            if row["rejection_reason"] is not None
            else None
        ),
    )


def _execution(row: aiosqlite.Row) -> SimulatedExecution:
    return SimulatedExecution(
        id=row["execution_id"],
        order_id=row["order_id"],
        timestamp=_datetime(row["timestamp"]),
        side=OrderSide(row["side"]),
        reference_price=_decimal(row["reference_price"], name="execution.reference_price"),
        execution_price=_decimal(row["execution_price"], name="execution.execution_price"),
        quantity=_decimal(row["quantity"], name="execution.quantity"),
        gross_notional=_decimal(row["gross_notional"], name="execution.gross_notional"),
        fee=_decimal(row["fee"], name="execution.fee"),
        slippage_rate=_decimal(row["slippage_rate"], name="execution.slippage_rate"),
    )


def _trade(row: aiosqlite.Row) -> StoredTrade:
    return StoredTrade(
        sequence=int(row["sequence"]),
        trade=SimulatedTrade(
            id=row["trade_id"],
            position_id=row["position_id"],
            symbol=row["symbol"],
            quote_asset=row["quote_asset"],
            entry_observation_id=row["entry_observation_id"],
            exit_observation_id=row["exit_observation_id"],
            entry_order_id=row["entry_order_id"],
            exit_order_id=row["exit_order_id"],
            entry_execution_id=row["entry_execution_id"],
            exit_execution_id=row["exit_execution_id"],
            entry_time=_datetime(row["entry_time"]),
            exit_time=_datetime(row["exit_time"]),
            entry_price=_decimal(row["entry_price"], name="trade.entry_price"),
            exit_price=_decimal(row["exit_price"], name="trade.exit_price"),
            quantity=_decimal(row["quantity"], name="trade.quantity"),
            entry_fee=_decimal(row["entry_fee"], name="trade.entry_fee"),
            exit_fee=_decimal(row["exit_fee"], name="trade.exit_fee"),
            gross_exit_proceeds=_decimal(
                row["gross_exit_proceeds"], name="trade.gross_exit_proceeds"
            ),
            net_exit_proceeds=_decimal(row["net_exit_proceeds"], name="trade.net_exit_proceeds"),
            realized_pnl=_decimal(row["realized_pnl"], name="trade.realized_pnl"),
            return_ratio=_decimal(row["return_ratio"], name="trade.return_ratio"),
            duration_bars=int(row["duration_bars"]),
            exit_reason=ExitReason(row["exit_reason"]),
        ),
    )


def _equity(row: aiosqlite.Row) -> StoredEquityPoint:
    return StoredEquityPoint(
        sequence=int(row["sequence"]),
        point=EquityPoint(
            timestamp=_datetime(row["timestamp"]),
            cash=_decimal(row["cash"], name="equity.cash"),
            position_value=_decimal(row["position_value"], name="equity.position_value"),
            equity=_decimal(row["equity"], name="equity.equity"),
            realized_pnl_cumulative=_decimal(
                row["realized_pnl_cumulative"],
                name="equity.realized_pnl_cumulative",
            ),
            unrealized_pnl=_decimal(row["unrealized_pnl"], name="equity.unrealized_pnl"),
            fees_cumulative=_decimal(row["fees_cumulative"], name="equity.fees_cumulative"),
            drawdown_ratio=_decimal(row["drawdown_ratio"], name="equity.drawdown_ratio"),
            exposed=bool(row["exposed"]),
        ),
    )


def _order_storage_row(job_id: str, sequence: int, item: SimulatedOrder) -> tuple[Any, ...]:
    return (
        job_id,
        PORTFOLIO_SCHEMA_VERSION,
        sequence,
        item.id,
        item.observation_id,
        item.side.value,
        _timestamp(item.intent_time),
        item.execution_policy.value,
        canonical_decimal(item.requested_cash) if item.requested_cash is not None else None,
        item.status.value,
        item.rejection_reason.value if item.rejection_reason else None,
    )


def _execution_storage_row(job_id: str, sequence: int, item: SimulatedExecution) -> tuple[Any, ...]:
    return (
        job_id,
        PORTFOLIO_SCHEMA_VERSION,
        sequence,
        item.id,
        item.order_id,
        _timestamp(item.timestamp),
        item.side.value,
        canonical_decimal(item.reference_price),
        canonical_decimal(item.execution_price),
        canonical_decimal(item.quantity),
        canonical_decimal(item.gross_notional),
        canonical_decimal(item.fee),
        canonical_decimal(item.slippage_rate),
    )


def _trade_storage_row(job_id: str, sequence: int, item: SimulatedTrade) -> tuple[Any, ...]:
    return (
        job_id,
        PORTFOLIO_SCHEMA_VERSION,
        sequence,
        item.id,
        item.position_id,
        item.symbol,
        item.quote_asset,
        item.entry_observation_id,
        item.exit_observation_id,
        item.entry_order_id,
        item.exit_order_id,
        item.entry_execution_id,
        item.exit_execution_id,
        _timestamp(item.entry_time),
        _timestamp(item.exit_time),
        canonical_decimal(item.entry_price),
        canonical_decimal(item.exit_price),
        canonical_decimal(item.quantity),
        canonical_decimal(item.entry_fee),
        canonical_decimal(item.exit_fee),
        canonical_decimal(item.gross_exit_proceeds),
        canonical_decimal(item.net_exit_proceeds),
        canonical_decimal(item.realized_pnl),
        canonical_decimal(item.return_ratio),
        item.duration_bars,
        item.exit_reason.value,
    )


def _equity_storage_row(job_id: str, sequence: int, item: EquityPoint) -> tuple[Any, ...]:
    return (
        job_id,
        PORTFOLIO_SCHEMA_VERSION,
        sequence,
        _timestamp(item.timestamp),
        canonical_decimal(item.cash),
        canonical_decimal(item.position_value),
        canonical_decimal(item.equity),
        canonical_decimal(item.realized_pnl_cumulative),
        canonical_decimal(item.unrealized_pnl),
        canonical_decimal(item.fees_cumulative),
        canonical_decimal(item.drawdown_ratio),
        int(item.exposed),
    )


class PortfolioRepository:
    """Repository sans dépendance FastAPI, adossé à la base applicative."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def replace_simulation_result(
        self,
        *,
        job_id: str,
        result: PortfolioSimulationResult,
        config_fingerprint: str,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> None:
        """Remplace un run dans une transaction unique et des lots bornés."""
        if not job_id or not config_fingerprint:
            raise PortfolioPersistenceError("portfolio_persistence_failed")
        created_at = (
            result.equity_curve[0].timestamp
            if result.equity_curve
            else datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
        completed_at = result.equity_curve[-1].timestamp if result.equity_curve else created_at
        async with self.database.connection() as connection:
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    "DELETE FROM backtest_portfolio_runs WHERE job_id=?", (job_id,)
                )
                await connection.execute(
                    """
                    INSERT INTO backtest_portfolio_runs (
                        job_id, schema_version, engine_version, config_fingerprint,
                        quote_asset, config_json, metrics_json, final_cash,
                        final_equity, final_open_position_json, order_count,
                        execution_count, trade_count, equity_point_count,
                        created_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        PORTFOLIO_SCHEMA_VERSION,
                        PORTFOLIO_ENGINE_VERSION,
                        config_fingerprint,
                        result.quote_asset,
                        _json(asdict(result.config)),
                        _json(asdict(result.metrics)),
                        canonical_decimal(result.final_cash),
                        canonical_decimal(result.final_equity),
                        (
                            _json(asdict(result.final_open_position))
                            if result.final_open_position is not None
                            else None
                        ),
                        len(result.orders),
                        len(result.executions),
                        len(result.trades),
                        len(result.equity_curve),
                        _timestamp(created_at),
                        _timestamp(completed_at),
                    ),
                )
                statements: tuple[
                    tuple[
                        str,
                        Sequence[Any],
                        Callable[[str, int, Any], tuple[Any, ...]],
                    ],
                    ...,
                ] = (
                    (
                        """
                        INSERT INTO backtest_portfolio_orders (
                            job_id, schema_version, sequence, order_id,
                            observation_id, side, intent_time, execution_policy,
                            requested_cash, status, rejection_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        result.orders,
                        _order_storage_row,
                    ),
                    (
                        """
                        INSERT INTO backtest_portfolio_executions (
                            job_id, schema_version, sequence, execution_id,
                            order_id, timestamp, side, reference_price,
                            execution_price, quantity, gross_notional, fee,
                            slippage_rate
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        result.executions,
                        _execution_storage_row,
                    ),
                    (
                        """
                        INSERT INTO backtest_portfolio_trades (
                            job_id, schema_version, sequence, trade_id,
                            position_id, symbol, quote_asset,
                            entry_observation_id, exit_observation_id,
                            entry_order_id, exit_order_id, entry_execution_id,
                            exit_execution_id, entry_time, exit_time,
                            entry_price, exit_price, quantity, entry_fee,
                            exit_fee, gross_exit_proceeds, net_exit_proceeds,
                            realized_pnl, return_ratio, duration_bars, exit_reason
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        result.trades,
                        _trade_storage_row,
                    ),
                    (
                        """
                        INSERT INTO backtest_portfolio_equity (
                            job_id, schema_version, sequence, timestamp, cash,
                            position_value, equity, realized_pnl_cumulative,
                            unrealized_pnl, fees_cumulative, drawdown_ratio,
                            exposed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        result.equity_curve,
                        _equity_storage_row,
                    ),
                )
                for statement, items, row_builder in statements:
                    for start in range(0, len(items), PORTFOLIO_WRITE_BATCH_SIZE):
                        if cancellation_requested and cancellation_requested():
                            raise asyncio.CancelledError
                        batch = [
                            row_builder(job_id, start + offset, item)
                            for offset, item in enumerate(
                                items[start : start + PORTFOLIO_WRITE_BATCH_SIZE]
                            )
                        ]
                        await connection.executemany(statement, batch)
                expected = {
                    "backtest_portfolio_orders": len(result.orders),
                    "backtest_portfolio_executions": len(result.executions),
                    "backtest_portfolio_trades": len(result.trades),
                    "backtest_portfolio_equity": len(result.equity_curve),
                }
                for table, count in expected.items():
                    cursor = await connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE job_id=?", (job_id,)
                    )
                    row = await cursor.fetchone()
                    if row is None or int(row[0]) != count:
                        raise PortfolioPersistenceError("portfolio_persistence_failed")
                await connection.commit()
            except asyncio.CancelledError:
                await connection.rollback()
                raise
            except PortfolioPersistenceError:
                await connection.rollback()
                raise
            except Exception as exc:
                await connection.rollback()
                raise PortfolioPersistenceError("portfolio_persistence_failed") from exc

    async def get_run_metadata(self, job_id: str) -> StoredPortfolioRun | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM backtest_portfolio_runs WHERE job_id=?", (job_id,)
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        if int(row["schema_version"]) != PORTFOLIO_SCHEMA_VERSION:
            raise PortfolioPersistenceError("portfolio_persistence_failed")
        return StoredPortfolioRun(
            job_id=row["job_id"],
            schema_version=int(row["schema_version"]),
            engine_version=row["engine_version"],
            config_fingerprint=row["config_fingerprint"],
            quote_asset=row["quote_asset"],
            config=_config_from_json(row["config_json"]),
            metrics=_metrics_from_json(row["metrics_json"]),
            final_cash=_decimal(row["final_cash"], name="final_cash"),
            final_equity=_decimal(row["final_equity"], name="final_equity"),
            final_open_position=_position_from_json(row["final_open_position_json"]),
            order_count=int(row["order_count"]),
            execution_count=int(row["execution_count"]),
            trade_count=int(row["trade_count"]),
            equity_point_count=int(row["equity_point_count"]),
            created_at=_datetime(row["created_at"]),
            completed_at=_datetime(row["completed_at"]),
        )

    async def list_trades(self, *, job_id: str, offset: int, limit: int) -> StoredTradePage:
        async with self.database.connection() as connection:
            count_cursor = await connection.execute(
                "SELECT COUNT(*) FROM backtest_portfolio_trades WHERE job_id=?",
                (job_id,),
            )
            count_row = await count_cursor.fetchone()
            cursor = await connection.execute(
                """
                SELECT * FROM backtest_portfolio_trades
                WHERE job_id=? ORDER BY sequence ASC LIMIT ? OFFSET ?
                """,
                (job_id, limit, offset),
            )
            rows = await cursor.fetchall()
        return StoredTradePage(
            items=tuple(_trade(row) for row in rows),
            total=int(count_row[0]) if count_row else 0,
        )

    async def list_equity_points(self, *, job_id: str, offset: int, limit: int) -> StoredEquityPage:
        async with self.database.connection() as connection:
            count_cursor = await connection.execute(
                "SELECT COUNT(*) FROM backtest_portfolio_equity WHERE job_id=?",
                (job_id,),
            )
            count_row = await count_cursor.fetchone()
            cursor = await connection.execute(
                """
                SELECT * FROM backtest_portfolio_equity
                WHERE job_id=? ORDER BY sequence ASC LIMIT ? OFFSET ?
                """,
                (job_id, limit, offset),
            )
            rows = await cursor.fetchall()
        return StoredEquityPage(
            items=tuple(_equity(row) for row in rows),
            total=int(count_row[0]) if count_row else 0,
        )

    async def sample_equity_points(self, *, job_id: str, max_points: int) -> StoredEquityPage:
        """Sélectionne des lignes existantes sans matérialiser toute la courbe."""
        if max_points < 4 or max_points > PORTFOLIO_SAMPLE_MAX_POINTS:
            raise ValueError("max_points doit être compris entre 4 et 2000")
        metadata = await self.get_run_metadata(job_id)
        total = metadata.equity_point_count if metadata else 0
        if total <= max_points:
            return await self.list_equity_points(job_id=job_id, offset=0, limit=max_points)
        extrema: dict[str, tuple[int, Decimal] | None] = {
            "equity": None,
            "drawdown": None,
        }
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT sequence, equity, drawdown_ratio
                FROM backtest_portfolio_equity
                WHERE job_id=? ORDER BY sequence ASC
                """,
                (job_id,),
            )
            while True:
                rows = await cursor.fetchmany(PORTFOLIO_READ_BATCH_SIZE)
                if not rows:
                    break
                for row in rows:
                    sequence = int(row["sequence"])
                    equity = _decimal(row["equity"], name="equity.equity")
                    drawdown = _decimal(row["drawdown_ratio"], name="equity.drawdown_ratio")
                    if extrema["equity"] is None or equity > extrema["equity"][1]:
                        extrema["equity"] = (sequence, equity)
                    if extrema["drawdown"] is None or drawdown > extrema["drawdown"][1]:
                        extrema["drawdown"] = (sequence, drawdown)
        selected = {0, total - 1}
        selected.update(value[0] for value in extrema.values() if value is not None)
        remaining = max_points - len(selected)
        if remaining > 0:
            denominator = remaining + 1
            selected.update(
                round(index * (total - 1) / denominator) for index in range(1, denominator)
            )
        selected_sequences = sorted(selected)[:max_points]
        placeholders = ",".join("?" for _ in selected_sequences)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"""
                SELECT * FROM backtest_portfolio_equity
                WHERE job_id=? AND sequence IN ({placeholders})
                ORDER BY sequence ASC
                """,
                (job_id, *selected_sequences),
            )
            rows = await cursor.fetchall()
        return StoredEquityPage(
            items=tuple(_equity(row) for row in rows),
            total=total,
        )

    async def iter_trades(
        self, job_id: str, *, batch_size: int = PORTFOLIO_READ_BATCH_SIZE
    ) -> AsyncIterator[tuple[StoredTrade, ...]]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM backtest_portfolio_trades
                WHERE job_id=? ORDER BY sequence ASC
                """,
                (job_id,),
            )
            while True:
                rows = await cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield tuple(_trade(row) for row in rows)

    async def iter_equity_points(
        self, job_id: str, *, batch_size: int = PORTFOLIO_READ_BATCH_SIZE
    ) -> AsyncIterator[tuple[StoredEquityPoint, ...]]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM backtest_portfolio_equity
                WHERE job_id=? ORDER BY sequence ASC
                """,
                (job_id,),
            )
            while True:
                rows = await cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield tuple(_equity(row) for row in rows)

    async def load_portfolio_simulation_result(
        self, job_id: str
    ) -> PortfolioSimulationResult | None:
        metadata = await self.get_run_metadata(job_id)
        if metadata is None:
            return None
        async with self.database.connection() as connection:
            orders_cursor = await connection.execute(
                """
                SELECT * FROM backtest_portfolio_orders
                WHERE job_id=? ORDER BY sequence ASC
                """,
                (job_id,),
            )
            executions_cursor = await connection.execute(
                """
                SELECT * FROM backtest_portfolio_executions
                WHERE job_id=? ORDER BY sequence ASC
                """,
                (job_id,),
            )
            order_rows = list(await orders_cursor.fetchall())
            execution_rows = list(await executions_cursor.fetchall())
        trades: list[StoredTrade] = []
        async for trade_batch in self.iter_trades(job_id):
            trades.extend(trade_batch)
        equity: list[StoredEquityPoint] = []
        async for equity_batch in self.iter_equity_points(job_id):
            equity.extend(equity_batch)
        if (
            len(order_rows) != metadata.order_count
            or len(execution_rows) != metadata.execution_count
            or len(trades) != metadata.trade_count
            or len(equity) != metadata.equity_point_count
        ):
            raise PortfolioPersistenceError("portfolio_persistence_failed")
        return PortfolioSimulationResult(
            version=1,
            quote_asset=metadata.quote_asset,
            config=metadata.config,
            orders=tuple(_order(row) for row in order_rows),
            executions=tuple(_execution(row) for row in execution_rows),
            trades=tuple(item.trade for item in trades),
            equity_curve=tuple(item.point for item in equity),
            final_cash=metadata.final_cash,
            final_equity=metadata.final_equity,
            final_open_position=metadata.final_open_position,
            metrics=metadata.metrics,
        )

    async def delete_simulation_result(self, job_id: str) -> None:
        async with self.database.connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await connection.execute(
                    "DELETE FROM backtest_portfolio_runs WHERE job_id=?", (job_id,)
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
