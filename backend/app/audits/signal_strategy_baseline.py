"""Baseline descriptive et reproductible de la stratégie de signaux actuelle."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence, cast

from app.core.settings import ScanConfig, Timeframe
from app.database.connection import Database
from app.domain.candles import Candle, timeframe_milliseconds
from app.domain.portfolio import (
    OrderStatus,
    PortfolioSimulationConfig,
    PortfolioSimulationResult,
    PortfolioSimulationStep,
    SimulatedTrade,
    simulate_portfolio,
)
from app.models.backtest import BacktestConfig, BacktestJob, BacktestStatus, ForwardOutcome
from app.models.backtest import SignalObservation
from app.models.portfolio import PortfolioSimulationConfigV1
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.services.backtest_engine import BacktestEngine
from app.services.portfolio_replay import (
    backtest_config_fingerprint,
    build_portfolio_simulation_steps,
)

BASELINE_VERSION = "signal-strategy-baseline-v1"
INDICATORS = ("rsi", "sma", "ema", "macd", "bollinger", "stochastic")
FEE_MATRIX = ("0", "0.0005", "0.001", "0.002")
SLIPPAGE_MATRIX = ("0", "0.0005", "0.001", "0.002")
SIZING_MATRIX = ("25", "50", "100")
MIN_CANDLES = 500
MIN_TRADES = 30
MIN_CONTINUITY = Decimal("0.98")
SEGMENT_RATIOS = (Decimal("0.60"), Decimal("0.20"), Decimal("0.20"))


@dataclass(frozen=True, slots=True)
class DatasetInventory:
    exchange_id: str
    market_type: str
    symbol: str
    timeframe: str
    first_open_time: datetime
    last_open_time: datetime
    candle_count: int
    closed_candle_count: int
    gap_count: int
    expected_candle_count: int
    continuity_ratio: Decimal
    source: str

    @property
    def key(self) -> str:
        return f"{self.symbol}|{self.timeframe}"


@dataclass(frozen=True, slots=True)
class DatasetSelection:
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    candle_count: int
    continuity_ratio: Decimal
    reason: str

    @property
    def key(self) -> str:
        return f"{self.symbol}|{self.timeframe}"


@dataclass(frozen=True, slots=True)
class ChronologicalSegment:
    name: str
    start_index: int
    end_index: int
    start: datetime
    end: datetime


class ReadOnlyHistoricalRepository:
    """Repository minimal ouvrant SQLite en mode URI strictement read-only."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def _read(
        self,
        *,
        symbol: str,
        timeframe: str,
        before_ms: int | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int,
    ) -> list[Candle]:
        clauses = [
            "exchange_id='binance'",
            "market_type='spot'",
            "symbol=?",
            "timeframe=?",
            "is_closed=1",
        ]
        parameters: list[str | int] = [symbol, timeframe]
        descending = before_ms is not None
        if before_ms is not None:
            clauses.append("open_time < ?")
            parameters.append(before_ms)
        if start_ms is not None:
            clauses.append("open_time >= ?")
            parameters.append(start_ms)
        if end_ms is not None:
            clauses.append("open_time < ?")
            parameters.append(end_ms)
        parameters.append(limit)
        direction = "DESC" if descending else "ASC"
        sql = (
            "SELECT exchange_id,market_type,symbol,timeframe,open_time,open,high,low,"
            "close,volume,close_time,is_closed FROM candles WHERE "
            + " AND ".join(clauses)
            + f" ORDER BY open_time {direction} LIMIT ?"
        )
        with _read_only_connection(self.path) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        if descending:
            rows.reverse()
        return [
            Candle(
                exchange_id=str(row["exchange_id"]),
                market_type=str(row["market_type"]),
                symbol=str(row["symbol"]),
                timeframe=str(row["timeframe"]),
                open_time=int(row["open_time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                close_time=int(row["close_time"]) if row["close_time"] is not None else None,
                is_closed=bool(row["is_closed"]),
            )
            for row in rows
        ]

    async def before(
        self, symbol: str, timeframe: str, before_ms: int, limit: int, job: BacktestJob
    ) -> list[Candle]:
        del job
        return self._read(
            symbol=symbol,
            timeframe=timeframe,
            before_ms=before_ms,
            limit=limit,
        )

    async def range(
        self, symbol: str, timeframe: str, start_ms: int, end_ms: int, job: BacktestJob
    ) -> list[Candle]:
        del job
        return self._read(
            symbol=symbol,
            timeframe=timeframe,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=2_000_000,
        )

    def selected_candles(self, selection: DatasetSelection) -> list[Candle]:
        return self._read(
            symbol=selection.symbol,
            timeframe=selection.timeframe,
            start_ms=int(selection.start.timestamp() * 1_000),
            end_ms=int(selection.end.timestamp() * 1_000),
            limit=2_000_000,
        )


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _utc(milliseconds: int) -> datetime:
    return datetime.fromtimestamp(milliseconds / 1_000, timezone.utc)


def _decimal_text(value: Decimal | float | int | str | None) -> str | None:
    if value is None:
        return None
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    if decimal == 0:
        return "0"
    return format(decimal.normalize(), "f")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def inventory_datasets(path: Path) -> list[DatasetInventory]:
    """Inventorie toutes les combinaisons sans écrire dans la base historique."""
    with _read_only_connection(path) as connection:
        rows = connection.execute("""
            SELECT exchange_id,market_type,symbol,timeframe,open_time,is_closed
            FROM candles
            ORDER BY exchange_id,market_type,symbol,timeframe,open_time
            """).fetchall()
    grouped: dict[tuple[str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row["exchange_id"]),
                str(row["market_type"]),
                str(row["symbol"]),
                str(row["timeframe"]),
            )
        ].append(row)
    inventory: list[DatasetInventory] = []
    for (exchange_id, market_type, symbol, timeframe), items in grouped.items():
        timestamps = [int(item["open_time"]) for item in items]
        interval = timeframe_milliseconds(timeframe)
        gaps = sum(
            current - previous != interval for previous, current in zip(timestamps, timestamps[1:])
        )
        expected = (timestamps[-1] - timestamps[0]) // interval + 1 if timestamps else 0
        continuity = Decimal(len(timestamps)) / Decimal(expected) if expected else Decimal("0")
        inventory.append(
            DatasetInventory(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                first_open_time=_utc(timestamps[0]),
                last_open_time=_utc(timestamps[-1]),
                candle_count=len(items),
                closed_candle_count=sum(bool(item["is_closed"]) for item in items),
                gap_count=gaps,
                expected_candle_count=expected,
                continuity_ratio=continuity,
                source=str(path.resolve()),
            )
        )
    return inventory


def _continuous_runs(path: Path, item: DatasetInventory) -> list[tuple[int, int, int]]:
    with _read_only_connection(path) as connection:
        timestamps = [
            int(row[0])
            for row in connection.execute(
                """
                SELECT open_time FROM candles
                WHERE exchange_id=? AND market_type=? AND symbol=? AND timeframe=?
                  AND is_closed=1
                ORDER BY open_time
                """,
                (item.exchange_id, item.market_type, item.symbol, item.timeframe),
            )
        ]
    if not timestamps:
        return []
    interval = timeframe_milliseconds(item.timeframe)
    starts = [0]
    ends: list[int] = []
    for index, (previous, current) in enumerate(zip(timestamps, timestamps[1:])):
        if current - previous != interval:
            ends.append(index)
            starts.append(index + 1)
    ends.append(len(timestamps) - 1)
    return [
        (timestamps[start], timestamps[end], end - start + 1) for start, end in zip(starts, ends)
    ]


def select_datasets(
    path: Path, inventory: Sequence[DatasetInventory], *, mode: str
) -> list[DatasetSelection]:
    """Sélection pré-définie par profondeur et diversité, jamais par performance."""
    preferred = (
        (("BTC/USDC", "4h"),)
        if mode == "quick"
        else (
            ("BTC/USDC", "4h"),
            ("BTC/USDC", "1d"),
            ("LINK/USDC", "4h"),
            ("ONDO/USDC", "1h"),
            ("SUI/USDC", "1h"),
        )
    )
    by_key = {(item.symbol, item.timeframe): item for item in inventory}
    selected: list[DatasetSelection] = []
    for key in preferred:
        item = by_key.get(key)
        if item is None:
            continue
        runs = _continuous_runs(path, item)
        eligible = [run for run in runs if run[2] >= MIN_CANDLES]
        if not eligible:
            continue
        first_ms, last_ms, count = max(eligible, key=lambda run: (run[2], run[1]))
        # Le moteur contrôle aussi la jonction warm-up/plage. Écarter la première
        # bougie d'un run empêche qu'un gap antérieur soit attribué à la plage.
        interval = timeframe_milliseconds(item.timeframe)
        if count > MIN_CANDLES:
            first_ms += interval
            count -= 1
        if mode == "quick":
            count = min(count, 400)
            first_ms = last_ms - (count - 1) * interval
        selected.append(
            DatasetSelection(
                symbol=item.symbol,
                timeframe=item.timeframe,
                start=_utc(first_ms),
                end=_utc(last_ms + interval),
                candle_count=count,
                continuity_ratio=Decimal("1"),
                reason=(
                    "plus longue plage fermée contiguë; sélectionnée avant lecture "
                    "des performances pour profondeur/liquidité/diversité"
                ),
            )
        )
    return selected


def chronological_segments(
    timestamps: Sequence[datetime],
) -> tuple[ChronologicalSegment, ChronologicalSegment, ChronologicalSegment]:
    """Découpe 60/20/20 sans permutation et sans chevauchement."""
    if len(timestamps) < 5:
        raise ValueError("au moins cinq timestamps sont requis pour segmenter")
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ValueError("les timestamps doivent être strictement croissants")
    development_end = int(len(timestamps) * SEGMENT_RATIOS[0])
    validation_end = int(len(timestamps) * (SEGMENT_RATIOS[0] + SEGMENT_RATIOS[1]))
    bounds = (
        ("development", 0, development_end),
        ("validation", development_end, validation_end),
        ("test", validation_end, len(timestamps)),
    )
    return tuple(
        ChronologicalSegment(
            name=name,
            start_index=start,
            end_index=end,
            start=timestamps[start],
            end=timestamps[end - 1],
        )
        for name, start, end in bounds
    )  # type: ignore[return-value]


def descriptive_decimal(values: Iterable[Decimal]) -> dict[str, Any]:
    items = sorted(values)
    if not items:
        return {"count": 0}

    def quantile(ratio: Decimal) -> Decimal:
        index = int((len(items) - 1) * ratio)
        return items[index]

    return {
        "count": len(items),
        "minimum": items[0],
        "q10": quantile(Decimal("0.10")),
        "q25": quantile(Decimal("0.25")),
        "median": Decimal(str(statistics.median(items))),
        "q75": quantile(Decimal("0.75")),
        "q90": quantile(Decimal("0.90")),
        "maximum": items[-1],
        "mean": sum(items, Decimal("0")) / Decimal(len(items)),
    }


def profit_concentration(trades: Sequence[SimulatedTrade]) -> dict[str, Any]:
    """Contribution des extrêmes; le ratio reste nul si le P&L total ne le définit pas."""
    pnls = sorted((trade.realized_pnl for trade in trades), reverse=True)
    total = sum(pnls, Decimal("0"))

    def contribution(values: Sequence[Decimal]) -> dict[str, Any]:
        amount = sum(values, Decimal("0"))
        return {
            "pnl": amount,
            "share_of_total": amount / total if total != 0 else None,
            "share_interpretation": (
                "standard"
                if total > 0
                else "signed_against_non_positive_total" if total < 0 else "undefined_zero_total"
            ),
        }

    top_ten_percent = max(1, math.ceil(len(pnls) * 0.10)) if pnls else 0
    ascending = list(reversed(pnls))
    return {
        "total_pnl": total,
        "best_1": contribution(pnls[:1]),
        "best_3": contribution(pnls[:3]),
        "best_5": contribution(pnls[:5]),
        "best_10_percent": contribution(pnls[:top_ten_percent]),
        "worst_1": contribution(ascending[:1]),
        "worst_3": contribution(ascending[:3]),
        "worst_5": contribution(ascending[:5]),
        "worst_10_percent": contribution(ascending[:top_ten_percent]),
    }


def _maximum_streak(signs: Sequence[int], target: int) -> int:
    maximum = current = 0
    for sign in signs:
        current = current + 1 if sign == target else 0
        maximum = max(maximum, current)
    return maximum


def trade_diagnostics(trades: Sequence[SimulatedTrade]) -> dict[str, Any]:
    signs = [(trade.realized_pnl > 0) - (trade.realized_pnl < 0) for trade in trades]
    gaps = [
        Decimal(str((current.entry_time - previous.exit_time).total_seconds()))
        for previous, current in zip(trades, trades[1:])
    ]
    return {
        "pnl": descriptive_decimal(trade.realized_pnl for trade in trades),
        "return_ratio": descriptive_decimal(trade.return_ratio for trade in trades),
        "duration_bars": descriptive_decimal(Decimal(trade.duration_bars) for trade in trades),
        "fees": descriptive_decimal(trade.entry_fee + trade.exit_fee for trade in trades),
        "seconds_between_trades": descriptive_decimal(gaps),
        "maximum_winning_streak": _maximum_streak(signs, 1),
        "maximum_losing_streak": _maximum_streak(signs, -1),
    }


def _average_trade_duration(trades: Sequence[SimulatedTrade]) -> Decimal | None:
    if not trades:
        return None
    return sum((Decimal(item.duration_bars) for item in trades), Decimal("0")) / Decimal(
        len(trades)
    )


def _extended_metrics(result: PortfolioSimulationResult) -> dict[str, Any]:
    trades = result.trades
    wins = [item for item in trades if item.realized_pnl > 0]
    losses = [item for item in trades if item.realized_pnl < 0]
    gross_profit = sum((item.realized_pnl for item in wins), Decimal("0"))
    gross_loss = sum((item.realized_pnl for item in losses), Decimal("0"))
    return {
        **asdict(result.metrics),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss else None,
        "average_win": gross_profit / Decimal(len(wins)) if wins else None,
        "average_loss": gross_loss / Decimal(len(losses)) if losses else None,
        "largest_win": max((item.realized_pnl for item in wins), default=None),
        "largest_loss": min((item.realized_pnl for item in losses), default=None),
        "average_trade_duration": _average_trade_duration(trades),
    }


def _state_durations(observations: Sequence[SignalObservation], state: bool) -> dict[str, Any]:
    durations: list[Decimal] = []
    current = 0
    for item in observations:
        if item.accepted is state:
            current += 1
        elif current:
            durations.append(Decimal(current))
            current = 0
    if current:
        durations.append(Decimal(current))
    return descriptive_decimal(durations)


def observation_diagnostics(observations: Sequence[SignalObservation]) -> dict[str, Any]:
    transitions_up = transitions_down = 0
    for previous, current in zip(observations, observations[1:]):
        transitions_up += not previous.accepted and current.accepted
        transitions_down += previous.accepted and not current.accepted
    accepted = sum(item.accepted for item in observations)
    return {
        "observation_count": len(observations),
        "accepted_count": accepted,
        "rejected_count": len(observations) - accepted,
        "acceptance_ratio": (
            Decimal(accepted) / Decimal(len(observations)) if observations else None
        ),
        "false_to_true": transitions_up,
        "true_to_false": transitions_down,
        "accepted_state_duration_bars": _state_durations(observations, True),
        "rejected_state_duration_bars": _state_durations(observations, False),
        "rejection_stages": dict(Counter(item.rejection_stage or "none" for item in observations)),
        "rejection_reasons": dict(
            Counter(item.rejection_reason or "none" for item in observations)
        ),
    }


def order_diagnostics(result: PortfolioSimulationResult) -> dict[str, Any]:
    statuses = Counter(order.status.value for order in result.orders)
    reasons = Counter(
        order.rejection_reason.value
        for order in result.orders
        if order.rejection_reason is not None
    )
    return {
        "order_count": len(result.orders),
        "executed_count": statuses[OrderStatus.EXECUTED.value],
        "rejected_count": statuses[OrderStatus.REJECTED.value],
        "cancelled_count": statuses[OrderStatus.CANCELLED.value],
        "pending_count": statuses[OrderStatus.PENDING.value],
        "rejection_reasons": dict(reasons),
    }


def exit_diagnostics(trades: Sequence[SimulatedTrade]) -> dict[str, Any]:
    grouped: dict[str, list[SimulatedTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.exit_reason.value].append(trade)
    return {
        reason: {
            "trade_count": len(items),
            "total_return": sum((item.return_ratio for item in items), Decimal("0")),
            "average_return": (
                sum((item.return_ratio for item in items), Decimal("0")) / Decimal(len(items))
            ),
            "win_rate": Decimal(sum(item.realized_pnl > 0 for item in items)) / Decimal(len(items)),
            "average_duration_bars": _average_trade_duration(items),
            "total_pnl": sum((item.realized_pnl for item in items), Decimal("0")),
        }
        for reason, items in sorted(grouped.items())
    }


def indicator_diagnostics(
    observations: Sequence[SignalObservation], trades: Sequence[SimulatedTrade]
) -> dict[str, Any]:
    entry_ids = {trade.entry_observation_id for trade in trades}
    winning_ids = {trade.entry_observation_id for trade in trades if trade.realized_pnl > 0}
    losing_ids = {trade.entry_observation_id for trade in trades if trade.realized_pnl < 0}
    scopes = {
        "all": list(observations),
        "accepted": [item for item in observations if item.accepted],
        "entries": [item for item in observations if str(item.id) in entry_ids],
        "winning_entries": [item for item in observations if str(item.id) in winning_ids],
        "losing_entries": [item for item in observations if str(item.id) in losing_ids],
    }
    result: dict[str, Any] = {}
    trade_by_entry = {trade.entry_observation_id: trade for trade in trades}
    for name in INDICATORS:
        indicator: dict[str, Any] = {}
        for scope, items in scopes.items():
            statuses: Counter[str] = Counter()
            directions: Counter[str] = Counter()
            signals: Counter[str] = Counter()
            states: Counter[str] = Counter()
            strengths: list[Decimal] = []
            for observation in items:
                signal = observation.indicator_signals.get(name)
                status_value = getattr(signal.status, "value", signal.status) if signal else None
                status = str(status_value) if signal is not None else "missing"
                statuses[status] += 1
                if signal is not None:
                    directions[str(getattr(signal.direction, "value", signal.direction))] += 1
                    signals[signal.signal or "none"] += 1
                    states[signal.state or "none"] += 1
                    strengths.append(Decimal(str(signal.strength)))
            total = len(items)
            indicator[scope] = {
                "sample_size": total,
                "status": dict(statuses),
                "status_ratio": {
                    key: Decimal(value) / Decimal(total) if total else None
                    for key, value in statuses.items()
                },
                "direction": dict(directions),
                "signal": dict(signals),
                "state": dict(states),
                "strength": descriptive_decimal(strengths),
            }
        performance: dict[str, dict[str, dict[str, Any]]] = {}
        for field in ("direction", "signal", "state"):
            groups: dict[str, list[SimulatedTrade]] = defaultdict(list)
            for observation in observations:
                trade = trade_by_entry.get(str(observation.id))
                signal = observation.indicator_signals.get(name)
                if trade is None or signal is None:
                    continue
                raw_value = getattr(signal, field)
                value = getattr(raw_value, "value", raw_value) or "none"
                groups[str(value)].append(trade)
            performance[field] = {
                value: {
                    "trade_count": len(items),
                    "average_return": sum((item.return_ratio for item in items), Decimal("0"))
                    / Decimal(len(items)),
                    "total_pnl": sum((item.realized_pnl for item in items), Decimal("0")),
                }
                for value, items in sorted(groups.items())
            }
        indicator["entry_trade_performance"] = performance
        result[name] = indicator
    return result


def confluence_diagnostics(
    observations: Sequence[SignalObservation], trades: Sequence[SimulatedTrade]
) -> dict[str, Any]:
    entry_ids = {trade.entry_observation_id for trade in trades}
    winning_ids = {trade.entry_observation_id for trade in trades if trade.realized_pnl > 0}
    losing_ids = {trade.entry_observation_id for trade in trades if trade.realized_pnl < 0}
    exit_ids = {
        trade.exit_observation_id for trade in trades if trade.exit_observation_id is not None
    }

    def summarize(items: Sequence[SignalObservation]) -> dict[str, Any]:
        scores = [
            Decimal(str(item.confluence_score))
            for item in items
            if item.confluence_score is not None
        ]
        buckets = Counter(
            "low:<40" if score < 40 else "medium:40-69.999" if score < 70 else "high:>=70"
            for score in scores
        )
        return {
            "sample_size": len(items),
            "scores": descriptive_decimal(scores),
            "predefined_buckets": dict(buckets),
            "grades": dict(Counter(str(item.confluence_grade) for item in items)),
        }

    return {
        "all": summarize(observations),
        "entries": summarize([item for item in observations if str(item.id) in entry_ids]),
        "exits": summarize([item for item in observations if str(item.id) in exit_ids]),
        "winning_entries": summarize(
            [item for item in observations if str(item.id) in winning_ids]
        ),
        "losing_entries": summarize([item for item in observations if str(item.id) in losing_ids]),
    }


def trend_diagnostics(
    observations: Sequence[SignalObservation], trades: Sequence[SimulatedTrade]
) -> dict[str, Any]:
    trade_by_entry = {trade.entry_observation_id: trade for trade in trades}
    counts: Counter[str] = Counter()
    performance: dict[str, list[SimulatedTrade]] = defaultdict(list)
    for observation in observations:
        state = (
            ",".join(
                sorted(
                    {
                        str(getattr(value, "value", value))
                        for value in observation.trend_states.values()
                    }
                )
            )
            or "none"
        )
        counts[state] += 1
        trade = trade_by_entry.get(str(observation.id))
        if trade is not None:
            performance[state].append(trade)
    return {
        "provenance": (
            "SignalObservation.trend_states "
            "(facteur historique multi-timeframe, distinct de SMA/EMA structurés)"
        ),
        "observation_states": dict(counts),
        "entry_trade_performance": {
            state: {
                "trade_count": len(items),
                "average_return": sum((item.return_ratio for item in items), Decimal("0"))
                / Decimal(len(items)),
                "total_pnl": sum((item.realized_pnl for item in items), Decimal("0")),
            }
            for state, items in sorted(performance.items())
        },
    }


def outcome_diagnostics(
    observations: Sequence[SignalObservation], outcomes: Sequence[ForwardOutcome]
) -> dict[str, Any]:
    by_id = {item.id: item for item in observations}
    grouped: dict[int, list[ForwardOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.horizon].append(outcome)
    result: dict[str, Any] = {}
    for horizon, items in sorted(grouped.items()):
        valid = [
            item
            for item in items
            if item.valid and not item.censored and item.net_return is not None
        ]
        accepted = [
            item
            for item in valid
            if by_id.get(item.observation_id) is not None and by_id[item.observation_id].accepted
        ]
        rejected = [item for item in valid if item not in accepted]

        def summarize(values: Sequence[ForwardOutcome]) -> dict[str, Any]:
            returns = [
                Decimal(str(item.net_return)) for item in values if item.net_return is not None
            ]
            return {
                **descriptive_decimal(returns),
                "positive_ratio": (
                    Decimal(sum(value > 0 for value in returns)) / Decimal(len(returns))
                    if returns
                    else None
                ),
                "mfe": descriptive_decimal(
                    Decimal(str(item.mfe)) for item in values if item.mfe is not None
                ),
                "mae": descriptive_decimal(
                    Decimal(str(item.mae)) for item in values if item.mae is not None
                ),
            }

        result[str(horizon)] = {
            "total": len(items),
            "censored": sum(item.censored for item in items),
            "all": summarize(valid),
            "accepted": summarize(accepted),
            "rejected": summarize(rejected),
        }
    return result


def _steps_for_segment(
    steps: Sequence[PortfolioSimulationStep], segment: ChronologicalSegment
) -> tuple[PortfolioSimulationStep, ...]:
    return tuple(steps[segment.start_index : segment.end_index])


def _simulate_matrix(
    *,
    symbol: str,
    steps: Sequence[PortfolioSimulationStep],
    canonical: PortfolioSimulationConfig,
) -> dict[str, Any]:
    result: dict[str, Any] = {"fees": {}, "slippage": {}, "sizing": {}}
    for fee in FEE_MATRIX:
        simulation = simulate_portfolio(
            symbol=symbol,
            steps=steps,
            config=replace(canonical, fee_rate=Decimal(fee)),
        )
        result["fees"][fee] = _extended_metrics(simulation)
    for slippage in SLIPPAGE_MATRIX:
        simulation = simulate_portfolio(
            symbol=symbol,
            steps=steps,
            config=replace(canonical, slippage_rate=Decimal(slippage)),
        )
        result["slippage"][slippage] = _extended_metrics(simulation)
    for sizing in SIZING_MATRIX:
        simulation = simulate_portfolio(
            symbol=symbol,
            steps=steps,
            config=replace(canonical, position_size_percent=Decimal(sizing)),
        )
        result["sizing"][sizing] = _extended_metrics(simulation)
    return result


def _robustness_status(metrics: dict[str, Any], concentration: dict[str, Any]) -> str:
    trades = int(metrics["trade_count"])
    total_return = Decimal(metrics["total_return_ratio"])
    top_five = concentration["best_5"]["share_of_total"]
    fees = Decimal(metrics["total_fees"])
    gross_profit = Decimal(metrics["gross_profit"])
    if trades < MIN_TRADES:
        return "faible échantillon"
    if total_return <= 0:
        return "non rentable"
    if gross_profit > 0 and fees / gross_profit > Decimal("0.50"):
        return "coûts trop élevés"
    if top_five is not None and Decimal(top_five) > Decimal("0.70"):
        return "dépendance à quelques trades"
    return "prometteur mais instable"


async def _run_selection(
    *,
    source: ReadOnlyHistoricalRepository,
    selection: DatasetSelection,
    temporary_database: Database,
    generated_at: datetime,
) -> dict[str, Any]:
    signal_config = ScanConfig(timeframe=cast(Timeframe, selection.timeframe), quote="USDC")
    config = BacktestConfig(
        symbols=[selection.symbol],
        start=selection.start,
        end=selection.end,
        signal_config=signal_config,
        horizons=[1, 3, 6, 12, 24],
        replay_mode="every_bar",
        entry_policy="next_open",
        gap_policy="reject_range",
        fee_bps=10,
        slippage_bps=0,
        snapshot_status="confirmed",
        portfolio_simulation=PortfolioSimulationConfigV1.model_validate(
            {
                "version": 1,
                "quote_asset": selection.symbol.rsplit("/", 1)[-1],
                "initial_capital": "10000",
                "position_sizing": {"mode": "percent_cash", "value": "100"},
                "execution_policy": "next_open",
                "fee_rate": "0.001",
                "slippage_rate": "0",
                "end_of_test_policy": "force_close",
            }
        ),
    )
    repositories = BacktestRepository(temporary_database)
    portfolios = PortfolioRepository(temporary_database)
    job_id = (
        "baseline-"
        + stable_fingerprint(
            {"dataset": asdict(selection), "config": config.model_dump(mode="json")}
        ).split(":", 1)[1][:16]
    )
    job = BacktestJob(
        id=job_id,
        status=BacktestStatus.RUNNING,
        config=config,
        created_at=generated_at,
        started_at=generated_at,
    )
    await repositories.save_job(job)
    engine = BacktestEngine(source, repositories, portfolios=portfolios, yield_every=250)
    await engine.run(job)
    observations = await repositories.all_observations(job.id)
    outcomes = await repositories.all_outcomes(job.id)
    portfolio = await portfolios.load_portfolio_simulation_result(job.id)
    if portfolio is None:
        raise RuntimeError(f"résultat portefeuille absent pour {selection.key}")
    candles = source.selected_candles(selection)
    steps = build_portfolio_simulation_steps(
        symbol=selection.symbol,
        timeframe=selection.timeframe,
        observations=observations,
        primary_candles=candles,
    )
    timestamps = [step.source_open_time for step in steps]
    segments = chronological_segments(timestamps)
    segment_results: dict[str, Any] = {}
    for segment in segments:
        simulation = simulate_portfolio(
            symbol=selection.symbol,
            steps=_steps_for_segment(steps, segment),
            config=portfolio.config,
        )
        segment_results[segment.name] = {
            "bounds": asdict(segment),
            "metrics": _extended_metrics(simulation),
            "trade_concentration": profit_concentration(simulation.trades),
            "sample_warning": (
                f"faible échantillon: {len(simulation.trades)} trades < {MIN_TRADES}"
                if len(simulation.trades) < MIN_TRADES
                else None
            ),
        }
    calendar_periods: dict[str, Any] = {}
    steps_by_year: dict[int, list[PortfolioSimulationStep]] = defaultdict(list)
    for step in steps:
        steps_by_year[step.source_open_time.year].append(step)
    for year, year_steps in sorted(steps_by_year.items()):
        if len(year_steps) < 5:
            continue
        simulation = simulate_portfolio(
            symbol=selection.symbol,
            steps=year_steps,
            config=portfolio.config,
        )
        calendar_periods[str(year)] = {
            "observation_count": len(year_steps),
            "metrics": _extended_metrics(simulation),
            "trade_concentration": profit_concentration(simulation.trades),
        }
    metrics = _extended_metrics(portfolio)
    concentration = profit_concentration(portfolio.trades)
    result = {
        "dataset": asdict(selection),
        "config_fingerprint": backtest_config_fingerprint(config),
        "dataset_fingerprint": job.dataset_version,
        "observation": observation_diagnostics(observations),
        "orders": order_diagnostics(portfolio),
        "portfolio_metrics": metrics,
        "exits": exit_diagnostics(portfolio.trades),
        "trade_distribution": trade_diagnostics(portfolio.trades),
        "trade_concentration": concentration,
        "indicators": indicator_diagnostics(observations, portfolio.trades),
        "confluence": confluence_diagnostics(observations, portfolio.trades),
        "trend": trend_diagnostics(observations, portfolio.trades),
        "outcomes": outcome_diagnostics(observations, outcomes),
        "segments": segment_results,
        "calendar_periods": calendar_periods,
        "outcomes_vs_portfolio": {
            "outcome_count": len(outcomes),
            "accepted_observation_count": sum(item.accepted for item in observations),
            "entry_trade_count": len(portfolio.trades),
            "accepted_observations_without_distinct_entry": max(
                0, sum(item.accepted for item in observations) - len(portfolio.trades)
            ),
            "note": (
                "les outcomes sont indépendants; le portefeuille ignore les répétitions "
                "accepted pendant une position et ne somme jamais les outcomes"
            ),
        },
        "sensitivity": _simulate_matrix(
            symbol=selection.symbol,
            steps=steps,
            canonical=portfolio.config,
        ),
        "existing_correlations": job.correlations or {},
        "existing_ablations": job.ablations or {},
        "robustness_status": _robustness_status(metrics, concentration),
        "sample_warning": (
            f"faible échantillon: {len(portfolio.trades)} trades < {MIN_TRADES}"
            if len(portfolio.trades) < MIN_TRADES
            else None
        ),
    }
    await repositories.delete_job(job.id)
    return result


def canonical_configuration(selection: DatasetSelection) -> dict[str, Any]:
    return {
        "replay_mode": "every_bar",
        "entry_policy": "next_open",
        "gap_policy": "reject_range",
        "snapshot_status": "confirmed",
        "horizons": [1, 3, 6, 12, 24],
        "signal_config": ScanConfig(
            timeframe=cast(Timeframe, selection.timeframe), quote="USDC"
        ).model_dump(mode="json"),
        "portfolio_simulation": {
            "version": 1,
            "strategy": "accepted_state_transition_v1",
            "quote_asset": selection.symbol.rsplit("/", 1)[-1],
            "initial_capital": "10000",
            "position_sizing": {"mode": "percent_cash", "value": "100"},
            "fee_rate": "0.001",
            "slippage_rate": "0",
            "execution_policy": "next_open",
            "end_of_test_policy": "force_close",
        },
    }


async def run_baseline(
    *,
    database_path: Path,
    mode: str,
    generated_at: datetime,
    git_head: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    inventory = inventory_datasets(database_path)
    selected = select_datasets(database_path, inventory, mode=mode)
    if not selected:
        return {
            "version": BASELINE_VERSION,
            "generated_at": generated_at,
            "git_head": git_head,
            "mode": mode,
            "inventory": [_jsonable(asdict(item)) for item in inventory],
            "selected": [],
            "results": [],
            "robustness_status": "non évaluable: aucune série sélectionnable",
            "duration_seconds": Decimal(str(round(time.perf_counter() - started, 6))),
        }
    source = ReadOnlyHistoricalRepository(database_path)
    with tempfile.TemporaryDirectory(prefix="signal-baseline-") as temporary:
        temporary_path = Path(temporary) / "audit-results.sqlite3"
        temporary_database = Database(temporary_path)
        await temporary_database.initialize()
        results = []
        for selection in selected:
            results.append(
                await _run_selection(
                    source=source,
                    selection=selection,
                    temporary_database=temporary_database,
                    generated_at=generated_at,
                )
            )
        await temporary_database.close()
    aggregate = {
        "candle_count": sum(item.candle_count for item in selected),
        "observation_count": sum(item["observation"]["observation_count"] for item in results),
        "accepted_count": sum(item["observation"]["accepted_count"] for item in results),
        "trade_count": sum(item["portfolio_metrics"]["trade_count"] for item in results),
        "net_profit_sum_non_combinable_accounts": sum(
            (item["portfolio_metrics"]["net_profit"] for item in results), Decimal("0")
        ),
        "total_fees_sum_non_combinable_accounts": sum(
            (item["portfolio_metrics"]["total_fees"] for item in results), Decimal("0")
        ),
    }
    payload = {
        "version": BASELINE_VERSION,
        "generated_at": generated_at,
        "git_head": git_head,
        "mode": mode,
        "network": False,
        "historical_database_read_only": True,
        "temporary_results_cleaned": True,
        "thresholds": {
            "minimum_candles": MIN_CANDLES,
            "minimum_trades": MIN_TRADES,
            "minimum_continuity": MIN_CONTINUITY,
        },
        "inventory": [asdict(item) for item in inventory],
        "selected": [asdict(item) for item in selected],
        "canonical_configs": {item.key: canonical_configuration(item) for item in selected},
        "aggregate_metrics": aggregate,
        "results": results,
        "duration_seconds": Decimal(str(round(time.perf_counter() - started, 6))),
    }
    payload["audit_fingerprint"] = stable_fingerprint(
        {
            "version": payload["version"],
            "git_head": git_head,
            "selected": payload["selected"],
            "canonical_configs": payload["canonical_configs"],
        }
    )
    return payload


def compact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    datasets = [
        {
            "symbol": item["dataset"]["symbol"],
            "timeframe": item["dataset"]["timeframe"],
            "start": item["dataset"]["start"],
            "end": item["dataset"]["end"],
            "candles": item["dataset"]["candle_count"],
            "config_fingerprint": item["config_fingerprint"],
            "metrics": item["portfolio_metrics"],
            "segments": {name: segment["metrics"] for name, segment in item["segments"].items()},
            "robustness_status": item["robustness_status"],
        }
        for item in payload["results"]
    ]
    return {
        "version": payload["version"],
        "generated_at": payload["generated_at"],
        "git_head": payload["git_head"],
        "config_fingerprint": payload.get("audit_fingerprint"),
        "datasets": datasets,
        "aggregate_metrics": payload.get("aggregate_metrics", {}),
        "robustness_status": (
            "insufficient_or_mixed"
            if any(item.get("sample_warning") for item in payload["results"])
            else "evaluable"
        ),
        "key_findings": build_findings(payload),
        "phase_7_2": phase72_recommendation(payload),
    }


def build_findings(payload: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    for item in payload["results"]:
        dataset = item["dataset"]
        metrics = item["portfolio_metrics"]
        findings.append(
            f"{dataset['symbol']} {dataset['timeframe']} "
            f"{dataset['start'].date().isoformat()}–{dataset['end'].date().isoformat()}: "
            f"{metrics['trade_count']} trades, rendement "
            f"{_decimal_text(metrics['total_return_ratio'])}, drawdown "
            f"{_decimal_text(metrics['max_drawdown_ratio'])}, statut "
            f"{item['robustness_status']}."
        )
    return findings


def phase72_recommendation(payload: dict[str, Any]) -> dict[str, str]:
    total_trades = sum(int(item["portfolio_metrics"]["trade_count"]) for item in payload["results"])
    rejection_stages: Counter[str] = Counter()
    for item in payload["results"]:
        rejection_stages.update(
            {
                stage: int(count)
                for stage, count in item["observation"].get("rejection_stages", {}).items()
                if stage != "none"
            }
        )
    if total_trades < MIN_TRADES and rejection_stages:
        stage, count = rejection_stages.most_common(1)[0]
        return {
            "target": f"goulot d'acceptation `{stage}`",
            "evidence": (
                f"{total_trades} trades au total et {count} rejets au stade `{stage}`; "
                "l'échantillon économique est insuffisant"
            ),
            "hypothesis": (
                f"une modification minimale du seul stade `{stage}` peut produire un "
                "échantillon évaluable sans dégrader fortement le drawdown"
            ),
        }
    return {
        "target": "règle de sortie `validation_lost`",
        "evidence": (
            f"{total_trades} trades permettent une première analyse économique; "
            "les sorties sont le prochain composant isolable sans toucher aux entrées"
        ),
        "hypothesis": (
            "une modification minimale de persistance de validation peut réduire "
            "les allers-retours et les coûts sans dégrader la validation"
        ),
    }


def _render_result_details(item: dict[str, Any]) -> str:
    dataset = item["dataset"]
    observation = item["observation"]
    orders = item["orders"]
    concentration = item["trade_concentration"]
    indicator_rows: list[str] = []
    for name, diagnostics in item["indicators"].items():
        all_scope = diagnostics["all"]
        entry_scope = diagnostics["entries"]
        indicator_rows.append(
            f"| {name} | {all_scope['sample_size']} | "
            f"{json.dumps(_jsonable(all_scope['status']), ensure_ascii=False)} | "
            f"{entry_scope['sample_size']} | "
            f"{json.dumps(_jsonable(entry_scope['direction']), ensure_ascii=False)} |"
        )
    outcome_rows: list[str] = []
    for horizon, values in item["outcomes"].items():
        outcome_rows.append(
            f"| {horizon} | {values['total']} | {values['censored']} | "
            f"{_decimal_text(values['all'].get('mean'))} | "
            f"{_decimal_text(values['all'].get('median'))} | "
            f"{_decimal_text(values['all'].get('positive_ratio'))} | "
            f"{_decimal_text(values['accepted'].get('mean'))} | "
            f"{_decimal_text(values['rejected'].get('mean'))} |"
        )
    sensitivity_rows: list[str] = []
    for family in ("fees", "slippage", "sizing"):
        for value, metrics in item["sensitivity"][family].items():
            sensitivity_rows.append(
                f"| {family} | {value} | {metrics['trade_count']} | "
                f"{_decimal_text(metrics['total_return_ratio'])} | "
                f"{_decimal_text(metrics['max_drawdown_ratio'])} | "
                f"{_decimal_text(metrics['total_fees'])} | "
                f"{_decimal_text(metrics['profit_factor'])} |"
            )
    period_rows = [
        f"| {period} | {values['observation_count']} | "
        f"{values['metrics']['trade_count']} | "
        f"{_decimal_text(values['metrics']['total_return_ratio'])} | "
        f"{_decimal_text(values['metrics']['max_drawdown_ratio'])} |"
        for period, values in item["calendar_periods"].items()
    ]
    ablation_rows = [
        f"| {label} | {', '.join(values['removed_factors'])} | "
        f"{values['accepted_count']} | {values['delta_vs_baseline']} |"
        for label, values in sorted(item["existing_ablations"].items())
    ]
    entry_performance = {
        name: diagnostics["entry_trade_performance"]
        for name, diagnostics in item["indicators"].items()
    }
    return f"""
### {dataset['symbol']} — {dataset['timeframe']}

Période `{dataset['start'].isoformat()}` à `{dataset['end'].isoformat()}` (fin
exclusive), {dataset['candle_count']} bougies.

#### Observations, transitions et ordres

- observations : {observation['observation_count']} ;
- accepted/rejected : {observation['accepted_count']}/{observation['rejected_count']}
  (taux {_decimal_text(observation['acceptance_ratio'])}) ;
- transitions false→true / true→false :
  {observation['false_to_true']}/{observation['true_to_false']} ;
- durées accepted : `{json.dumps(_jsonable(observation['accepted_state_duration_bars']), ensure_ascii=False)}` ;
- durées rejected : `{json.dumps(_jsonable(observation['rejected_state_duration_bars']), ensure_ascii=False)}` ;
- stades de rejet : `{json.dumps(observation['rejection_stages'], ensure_ascii=False, sort_keys=True)}` ;
- ordres total/exécutés/rejetés/annulés :
  {orders['order_count']}/{orders['executed_count']}/{orders['rejected_count']}/{orders['cancelled_count']} ;
- raisons opérationnelles : `{json.dumps(orders['rejection_reasons'], ensure_ascii=False, sort_keys=True)}`.

L'écart transitions/trades vient de `next_open`, des répétitions accepted, de
l'état de position, des ordres de fin de données et de `force_close`.

#### Sorties, distribution et concentration

Sorties : `{json.dumps(_jsonable(item['exits']), ensure_ascii=False, sort_keys=True)}`.

Distribution : `{json.dumps(_jsonable(item['trade_distribution']), ensure_ascii=False, sort_keys=True)}`.

| Extrême | P&L | Part du total | Interprétation |
|---|---:|---:|---|
| meilleur | {_decimal_text(concentration['best_1']['pnl'])} | {_decimal_text(concentration['best_1']['share_of_total'])} | {concentration['best_1']['share_interpretation']} |
| 3 meilleurs | {_decimal_text(concentration['best_3']['pnl'])} | {_decimal_text(concentration['best_3']['share_of_total'])} | {concentration['best_3']['share_interpretation']} |
| 5 meilleurs | {_decimal_text(concentration['best_5']['pnl'])} | {_decimal_text(concentration['best_5']['share_of_total'])} | {concentration['best_5']['share_interpretation']} |
| top 10 % | {_decimal_text(concentration['best_10_percent']['pnl'])} | {_decimal_text(concentration['best_10_percent']['share_of_total'])} | {concentration['best_10_percent']['share_interpretation']} |
| 5 pires | {_decimal_text(concentration['worst_5']['pnl'])} | {_decimal_text(concentration['worst_5']['share_of_total'])} | {concentration['worst_5']['share_interpretation']} |

#### Couverture, directions, signaux et states

| Indicateur | Observations | Statuts | Entrées | Directions aux entrées |
|---|---:|---|---:|---|
{chr(10).join(indicator_rows)}

Les associations direction/signal/state avec rendement et P&L des trades
d'entrée sont descriptives et gardent leur effectif :

```json
{json.dumps(_jsonable(entry_performance), ensure_ascii=False, indent=2, sort_keys=True)}
```

#### Confluence et tendance

Confluence (buckets fixés avant mesure) :

```json
{json.dumps(_jsonable(item['confluence']), ensure_ascii=False, indent=2, sort_keys=True)}
```

Tendance :

```json
{json.dumps(_jsonable(item['trend']), ensure_ascii=False, indent=2, sort_keys=True)}
```

#### Outcomes et horizons

| Horizon | Outcomes | Censurés | Moyenne | Médiane | Taux positif | Moy. accepted | Moy. rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(outcome_rows)}

Comparaison outcomes/portefeuille :
`{json.dumps(item['outcomes_vs_portfolio'], ensure_ascii=False, sort_keys=True)}`.

#### Périodes calendaires

| Année | Observations | Trades | Rendement | Drawdown |
|---|---:|---:|---:|---:|
{chr(10).join(period_rows) if period_rows else '| aucune période évaluable | 0 | 0 | n/a | n/a |'}

#### Sensibilité aux coûts et au sizing

| Famille | Valeur | Trades | Rendement | Drawdown | Frais | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(sensitivity_rows)}

#### Ablations et corrélations existantes

| Ablation | Facteurs retirés | Accepted | Delta |
|---|---|---:|---:|
{chr(10).join(ablation_rows) if ablation_rows else '| aucune | — | 0 | 0 |'}

Les ablations ci-dessus recalculent descriptivement la confluence et ses outcomes,
pas le portefeuille. Corrélations disponibles par horizon :
`{json.dumps(sorted(item['existing_correlations'].get('by_horizon', {})), ensure_ascii=False)}`.
Chaque matrice existante conserve ses `pair_counts`; aucune causalité n'est inférée.
"""


def render_markdown(payload: dict[str, Any]) -> str:
    selected_rows = []
    result_rows = []
    segment_rows = []
    for selection in payload["selected"]:
        selected_rows.append(
            f"| {selection['symbol']} | {selection['timeframe']} | "
            f"{selection['start'].date()} | {selection['end'].date()} | "
            f"{selection['candle_count']} | {_decimal_text(selection['continuity_ratio'])} |"
        )
    for item in payload["results"]:
        dataset = item["dataset"]
        metrics = item["portfolio_metrics"]
        result_rows.append(
            f"| {dataset['symbol']} | {dataset['timeframe']} | "
            f"{item['observation']['observation_count']} | "
            f"{item['observation']['accepted_count']} | {metrics['trade_count']} | "
            f"{_decimal_text(metrics['total_return_ratio'])} | "
            f"{_decimal_text(metrics['max_drawdown_ratio'])} | "
            f"{_decimal_text(metrics['win_rate'])} | "
            f"{_decimal_text(metrics['total_fees'])} | {item['robustness_status']} |"
        )
        for name, segment in item["segments"].items():
            segment_metrics = segment["metrics"]
            segment_rows.append(
                f"| {dataset['symbol']} | {dataset['timeframe']} | {name} | "
                f"{segment_metrics['trade_count']} | "
                f"{_decimal_text(segment_metrics['total_return_ratio'])} | "
                f"{_decimal_text(segment_metrics['max_drawdown_ratio'])} |"
            )
    findings = "\n".join(f"- {item}" for item in build_findings(payload))
    recommendation = phase72_recommendation(payload)
    details = "\n".join(
        _render_result_details(item) for item in payload["results"] if "orders" in item
    )
    return f"""# Baseline signaux et stratégie v1

## Résumé exécutif

Baseline de mesure uniquement au commit `{payload['git_head']}`. Aucun indicateur,
filtre, contrat public, endpoint ou code frontend n'est modifié. Les comptes de
chaque marché sont indépendants : leurs P&L ne forment pas un portefeuille
multi-actifs.

{findings or "- Aucune série évaluable."}

## Objectif et protocole

- configuration actuelle figée avant lecture des performances ;
- replay causal `every_bar`, exécution `next_open`, stratégie
  `accepted_state_transition_v1` ;
- découpage chronologique 60 % développement, 20 % validation, 20 % test final ;
- test final consulté seulement après gel de la configuration ;
- aucune optimisation, permutation aléatoire ou requête réseau ;
- base historique ouverte en lecture seule, résultats dans une SQLite temporaire supprimée.

## Code et empreintes

- Version : `{payload['version']}`
- Généré : `{_jsonable(payload['generated_at'])}`
- Git : `{payload['git_head']}`
- Empreinte d'audit : `{payload.get('audit_fingerprint', 'n/a')}`

## Inventaire des données

Combinaisons inventoriées : {len(payload['inventory'])}. Bougies locales :
{sum(item['candle_count'] for item in payload['inventory'])}. Les détails complets
restent produits par le script en mémoire ; le rapport suivi privilégie les séries
sélectionnées afin de rester compact.

| Symbole | Timeframe | Début | Fin exclusive | Bougies | Continuité |
|---|---|---:|---:|---:|---:|
{chr(10).join(selected_rows)}

Seuils pré-définis : au moins {MIN_CANDLES} bougies, continuité de la plage
sélectionnée au moins {_decimal_text(MIN_CONTINUITY)}, et au moins {MIN_TRADES}
trades pour éviter l'avertissement de faible échantillon.

## Configuration canonique

Capital 10 000 unités de cotation, sizing 100 % du cash, frais 0,1 %, slippage
nul, `next_open`, `force_close`, horizons 1/3/6/12/24 et paramètres
`ScanConfig` actuels. Les fingerprints par marché sont dans le résumé JSON.

## Résultats globaux et inter-marchés

| Symbole | TF | Observations | Accepted | Trades | Rendement | Drawdown | Win rate | Frais | Statut |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(result_rows)}

## Stabilité temporelle

| Symbole | TF | Segment | Trades | Rendement | Drawdown |
|---|---|---|---:|---:|---:|
{chr(10).join(segment_rows)}

Chaque résultat avec moins de {MIN_TRADES} trades est descriptif et non robuste.
Les bornes exactes, distributions, concentration des profits, ordres, sorties,
couverture des indicateurs, confluence, outcomes, sensibilités et ablations sont
conservés dans le calcul reproductible et synthétisés dans le JSON compact.

## Sensibilités et ablations

Les matrices sont fixées à l'avance : frais et slippage 0/0,05/0,1/0,2 %, sizing
25/50/100 %. Elles réutilisent exactement les mêmes observations et transitions.
Les ablations existantes de `build_analytics` sont rapportées comme analyses
d'outcomes ; elles ne sont pas assimilées à un P&L de portefeuille.

## Diagnostics détaillés par marché

{details}

## Limites méthodologiques

- Les historiques hors BTC sont courts et presque tous cotés en USDC.
- Une majorité des 851 combinaisons locales est non évaluable.
- Les catégories rares, corrélations et ablations sont descriptives, non causales.
- Le moteur v1 est mono-symbole, spot long-only, sans stop ni short.
- Les résultats du test final ne doivent servir à aucun réglage de cette baseline.

## Faiblesses, points robustes et éléments non concluants

Les faiblesses sont limitées aux faits chiffrés ci-dessus. Les garanties robustes
sont la causalité, la déterminisme, la séparation outcomes/portefeuille et la
sensibilité monotone attendue aux coûts. Les indicateurs ou catégories à faible
effectif restent non concluants et ne doivent pas être modifiés faute de preuve.

## Proposition unique de Phase 7.2

Expérience proposée : **{recommendation['target']}**. Preuve de sélection :
{recommendation['evidence']}. Hypothèse : {recommendation['hypothesis']}.

Métrique principale : rendement validation. Garde-fous : drawdown pas dégradé de
plus de 10 % relatif, nombre de trades au moins 80 % de la baseline, frais non
accrus, effet présent sur au moins deux marchés/périodes. Abandon : gain limité au
développement, test final consulté avant gel, ou dégradation d'un garde-fou.
Le test final demeure gelé jusqu'à la fin de cette future expérience. Cette
expérience n'est pas exécutée en Phase 7.1.
"""


def render_inventory_markdown(inventory: Sequence[DatasetInventory]) -> str:
    rows = [
        f"| {item.exchange_id} | {item.market_type} | {item.symbol} | "
        f"{item.timeframe} | {item.first_open_time.date()} | "
        f"{item.last_open_time.date()} | {item.candle_count} | {item.gap_count} | "
        f"{_decimal_text(item.continuity_ratio)} | SQLite locale |"
        for item in inventory
    ]
    return f"""# Inventaire historique de la baseline v1

Inventaire déterministe de la table `candles`, sans accès réseau ni écriture dans
la base. La continuité vaut `bougies / bougies attendues` entre les deux bornes ;
`gaps` compte les intervalles consécutifs différents de la durée exacte du
timeframe.

Combinaisons : {len(inventory)}. Bougies : {sum(item.candle_count for item in inventory)}.

| Exchange | Marché | Symbole | TF | Première | Dernière | Bougies | Gaps | Continuité | Source |
|---|---|---|---|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}
"""


def write_inventory(inventory: Sequence[DatasetInventory], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_inventory_markdown(inventory),
        encoding="utf-8",
        newline="\n",
    )
    return path


def write_outputs(payload: dict[str, Any], output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    markdown_path = output / "signal-strategy-baseline-v1.md"
    summary_path = output / "signal-strategy-baseline-v1-summary.json"
    markdown_path.write_text(render_markdown(payload), encoding="utf-8", newline="\n")
    summary_path.write_text(
        json.dumps(
            _jsonable(compact_summary(payload)),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if payload.get("mode") == "full":
        write_inventory(
            [DatasetInventory(**item) for item in payload["inventory"]],
            output / "signal-strategy-baseline-v1-inventory.md",
        )
    return markdown_path, summary_path


def run_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_baseline(**kwargs))
