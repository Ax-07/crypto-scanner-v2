"""Exports CSV v1 des détails de portefeuille, lus par lots."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator, Mapping, Sequence

from app.domain.portfolio.decimal_utils import canonical_decimal
from app.repositories.portfolio_repository import PortfolioRepository

TRADES_V1_COLUMNS = (
    "schema_version",
    "job_id",
    "trade_sequence",
    "trade_id",
    "position_id",
    "symbol",
    "quote_asset",
    "entry_observation_id",
    "exit_observation_id",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "quantity",
    "entry_fee",
    "exit_fee",
    "gross_exit_proceeds",
    "net_exit_proceeds",
    "realized_pnl",
    "return_ratio",
    "duration_bars",
    "exit_reason",
)

EQUITY_V1_COLUMNS = (
    "schema_version",
    "job_id",
    "sequence",
    "timestamp",
    "cash",
    "position_value",
    "equity",
    "realized_pnl_cumulative",
    "unrealized_pnl",
    "fees_cumulative",
    "drawdown_ratio",
)


def _csv_rows(columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\r\n")
    if not rows:
        writer.writeheader()
    else:
        writer.writerows(rows)
    return stream.getvalue()


async def stream_trades_v1(repository: PortfolioRepository, job_id: str) -> AsyncIterator[str]:
    """Produit l'en-tête puis les trades sans liste globale."""
    yield _csv_rows(TRADES_V1_COLUMNS, ())
    async for batch in repository.iter_trades(job_id):
        rows = []
        for stored in batch:
            trade = stored.trade
            rows.append(
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "trade_sequence": stored.sequence,
                    "trade_id": trade.id,
                    "position_id": trade.position_id,
                    "symbol": trade.symbol,
                    "quote_asset": trade.quote_asset,
                    "entry_observation_id": trade.entry_observation_id,
                    "exit_observation_id": trade.exit_observation_id or "",
                    "entry_time": trade.entry_time.isoformat().replace("+00:00", "Z"),
                    "exit_time": trade.exit_time.isoformat().replace("+00:00", "Z"),
                    "entry_price": canonical_decimal(trade.entry_price),
                    "exit_price": canonical_decimal(trade.exit_price),
                    "quantity": canonical_decimal(trade.quantity),
                    "entry_fee": canonical_decimal(trade.entry_fee),
                    "exit_fee": canonical_decimal(trade.exit_fee),
                    "gross_exit_proceeds": canonical_decimal(trade.gross_exit_proceeds),
                    "net_exit_proceeds": canonical_decimal(trade.net_exit_proceeds),
                    "realized_pnl": canonical_decimal(trade.realized_pnl),
                    "return_ratio": canonical_decimal(trade.return_ratio),
                    "duration_bars": trade.duration_bars,
                    "exit_reason": trade.exit_reason.value,
                }
            )
        yield _csv_rows(TRADES_V1_COLUMNS, rows)


async def stream_equity_v1(repository: PortfolioRepository, job_id: str) -> AsyncIterator[str]:
    """Produit la courbe brute complète avec une lecture SQLite bornée."""
    yield _csv_rows(EQUITY_V1_COLUMNS, ())
    async for batch in repository.iter_equity_points(job_id):
        rows = []
        for stored in batch:
            point = stored.point
            rows.append(
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "sequence": stored.sequence,
                    "timestamp": point.timestamp.isoformat().replace("+00:00", "Z"),
                    "cash": canonical_decimal(point.cash),
                    "position_value": canonical_decimal(point.position_value),
                    "equity": canonical_decimal(point.equity),
                    "realized_pnl_cumulative": canonical_decimal(point.realized_pnl_cumulative),
                    "unrealized_pnl": canonical_decimal(point.unrealized_pnl),
                    "fees_cumulative": canonical_decimal(point.fees_cumulative),
                    "drawdown_ratio": canonical_decimal(point.drawdown_ratio),
                }
            )
        yield _csv_rows(EQUITY_V1_COLUMNS, rows)
