"""Orchestration bornée du backfill OHLCV historique."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from app.core.exceptions import BackfillPaginationError
from app.core.settings import PROJECT_TIMEFRAMES
from app.domain.candles import timeframe_milliseconds
from app.models.backfill import (
    BackfillOptions,
    BackfillReport,
    BackfillStatus,
    SyncState,
    TargetResult,
)
from app.repositories.backfill_repository import BackfillRepository, now_ms
from app.repositories.candle_repository import CandleRepository
from app.services.candle_sync import CandleSyncService
from app.services.market_catalog import MarketCatalogService

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int, TargetResult], Awaitable[None]]


def select_timeframes(exchange: Any, requested: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Retourne l'intersection projet/exchange dans un ordre stable, du plus long au plus court."""
    unknown = set(requested) - set(PROJECT_TIMEFRAMES)
    if unknown:
        raise ValueError(f"Timeframes inconnus: {sorted(unknown)}")
    if getattr(exchange, "has", {}).get("fetchOHLCV") is False:
        raise ValueError("fetch_ohlcv n'est pas annoncé par l'exchange")
    available = set(getattr(exchange, "timeframes", {}) or {})
    candidates = list(requested or PROJECT_TIMEFRAMES)
    selected = [item for item in candidates if item in available]
    selected.sort(key=timeframe_milliseconds, reverse=True)
    skipped = sorted(set(candidates) - set(selected), key=candidates.index)
    if not selected:
        raise ValueError("Aucun timeframe demandé n'est pris en charge par l'exchange")
    return selected, skipped


class CandleBackfillService:
    """Télécharge des cibles via une file bornée et un exchange partagé."""

    def __init__(
        self,
        candle_repository: CandleRepository,
        state_repository: BackfillRepository,
        catalog_service: MarketCatalogService,
        sync_service: CandleSyncService,
        database_path: Path,
    ) -> None:
        self.candles = candle_repository
        self.states = state_repository
        self.catalog = catalog_service
        self.sync = sync_service
        self.database_path = database_path

    async def run(
        self,
        exchange: Any,
        options: BackfillOptions,
        progress: ProgressCallback | None = None,
    ) -> BackfillReport:
        """Prépare une simulation ou exécute le backfill et produit son rapport."""
        started = now_ms()
        run_id = uuid4().hex
        markets = await self.catalog.discover(
            exchange,
            exchange_id=options.exchange_id,
            market_type=options.market_type,
            quote=options.quote,
            include_inactive=options.include_inactive,
            persist=options.execute,
        )
        discovered = len(markets)
        symbols = (
            sorted(set(options.symbols))
            if options.symbols
            else [market.symbol for market in markets]
        )
        known = {market.symbol for market in markets}
        missing_symbols = set(symbols) - known
        if missing_symbols:
            raise ValueError(f"Symboles absents du catalogue: {sorted(missing_symbols)}")
        timeframes, skipped = select_timeframes(exchange, options.timeframes)
        targets = [(symbol, timeframe) for symbol in symbols for timeframe in timeframes]
        usage = shutil.disk_usage(self.database_path.parent)
        report = BackfillReport(
            run_id=run_id,
            exchange_id=options.exchange_id,
            market_type=options.market_type,
            quote=options.quote,
            execute=options.execute,
            discovered_symbols=discovered,
            selected_symbols=symbols,
            selected_timeframes=timeframes,
            skipped_timeframes=skipped,
            total_targets=len(targets),
            database_size_bytes=(
                self.database_path.stat().st_size if self.database_path.exists() else 0
            ),
            free_space_bytes=usage.free,
            started_at=started,
            database_file=self.database_path.name,
            resume_command="python -m app.cli.backfill_candles --resume --execute",
        )
        if not options.execute:
            for symbol, timeframe in targets:
                count = await self.candles.count(
                    options.exchange_id, options.market_type, symbol, timeframe
                )
                report.results.append(
                    TargetResult(
                        symbol,
                        timeframe,
                        BackfillStatus.PARTIAL if count else BackfillStatus.PENDING,
                        candles=count,
                        earliest=await self.candles.get_first_open_time(
                            options.exchange_id,
                            options.market_type,
                            symbol,
                            timeframe,
                        ),
                        latest=await self.candles.get_last_open_time(
                            options.exchange_id,
                            options.market_type,
                            symbol,
                            timeframe,
                        ),
                    )
                )
            report.completed_at = now_ms()
            return report

        await self.states.create_run(
            run_id,
            options.exchange_id,
            options.market_type,
            options.quote,
            len(targets),
            options.as_json_dict(),
        )
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue(
            maxsize=max(1, options.max_concurrency * 2)
        )
        results: list[TargetResult] = []
        result_lock = asyncio.Lock()

        async def worker() -> None:
            while True:
                target = await queue.get()
                try:
                    if target is None:
                        return

                    async def page_progress(update: TargetResult) -> None:
                        if progress is not None:
                            await progress(len(results), len(targets), update)

                    result = await self._run_target(
                        exchange, options, *target, page_progress=page_progress
                    )
                    async with result_lock:
                        results.append(result)
                        completed = len(results)
                    if progress is not None:
                        await progress(completed, len(targets), result)
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(options.max_concurrency)]
        try:
            for target in targets:
                await queue.put(target)
            for _ in workers:
                await queue.put(None)
            await queue.join()
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            await self._finish_run(run_id, results, BackfillStatus.INTERRUPTED)
            raise

        report.results = sorted(results, key=lambda item: (item.symbol, item.timeframe))
        report.completed_at = now_ms()
        final_status = (
            BackfillStatus.PARTIAL
            if any(item.status is not BackfillStatus.COMPLETED for item in results)
            else BackfillStatus.COMPLETED
        )
        await self._finish_run(run_id, results, final_status)
        return report

    async def _run_target(
        self,
        exchange: Any,
        options: BackfillOptions,
        symbol: str,
        timeframe: str,
        page_progress: Callable[[TargetResult], Awaitable[None]] | None = None,
    ) -> TargetResult:
        """Télécharge une cible et checkpoint chaque page validée."""
        interval = timeframe_milliseconds(timeframe)
        if options.restart:
            await self.states.reset_state(
                options.exchange_id, options.market_type, symbol, timeframe
            )
        state = await self.states.get_state(
            options.exchange_id, options.market_type, symbol, timeframe
        )
        if state is None:
            state = SyncState(
                exchange_id=options.exchange_id,
                market_type=options.market_type,
                symbol=symbol,
                timeframe=timeframe,
            )
        state.status = BackfillStatus.RUNNING
        state.started_at = state.started_at or now_ms()
        state.requested_to = options.to_time or now_ms() + interval

        try:
            existing_last = await self.candles.get_last_open_time(
                options.exchange_id, options.market_type, symbol, timeframe
            )
            earliest: int | None
            if options.from_time is not None:
                earliest = options.from_time
            elif state.earliest_available_time is not None and options.resume:
                earliest = state.earliest_available_time
            else:
                earliest = await self.find_earliest(exchange, options, symbol, timeframe)
            if earliest is None:
                state.status = BackfillStatus.PARTIAL
                state.last_error = "Aucune bougie disponible"
                state.completed_at = now_ms()
                await self.states.save_state(state)
                return TargetResult(symbol, timeframe, state.status, error=state.last_error)

            state.earliest_available_time = earliest
            state.requested_from = earliest
            if options.restart:
                cursor = earliest
            elif options.resume and existing_last is not None:
                cursor = max(earliest, existing_last - interval * (options.overlap_candles - 1))
                if state.next_since is not None:
                    cursor = min(cursor, max(earliest, state.next_since - interval))
            elif options.mode == "sync" and existing_last is not None:
                cursor = max(earliest, existing_last - interval)
            else:
                cursor = earliest
            end = state.requested_to
            previous_last: int | None = None
            last_progress = 0.0

            while end is not None and cursor < end:
                rows = await self.sync.fetch_page(
                    exchange,
                    symbol,
                    timeframe,
                    cursor,
                    options.page_limit,
                    options.max_retries,
                    options.retry_delay_seconds,
                )
                if not rows:
                    break
                page_candles = self.sync.normalize_page(
                    rows,
                    exchange_id=options.exchange_id,
                    market_type=options.market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                if page_candles[-1].open_time < cursor:
                    raise BackfillPaginationError(f"Page répétée pour {symbol} {timeframe}")
                normalized = [
                    candle
                    for candle in page_candles
                    if candle.open_time >= state.requested_from and candle.open_time < end
                ]
                if not normalized:
                    break
                last = normalized[-1].open_time
                if last < cursor or (previous_last is not None and last <= previous_last):
                    raise BackfillPaginationError(f"Pagination immobile pour {symbol} {timeframe}")
                previous_last = last
                upserted = await self.candles.upsert_many(normalized)
                state.pages_downloaded += 1
                state.candles_downloaded += len(rows)
                state.candles_upserted += upserted
                state.latest_available_time = last
                state.next_since = last + interval
                await self.states.save_state(state)
                cursor = last + interval
                monotonic_now = time.monotonic()
                if (
                    page_progress is not None
                    and monotonic_now - last_progress >= options.progress_interval_seconds
                ):
                    await page_progress(
                        TargetResult(
                            symbol,
                            timeframe,
                            BackfillStatus.RUNNING,
                            pages=state.pages_downloaded,
                            candles=state.candles_upserted,
                            earliest=state.earliest_available_time,
                            latest=state.latest_available_time,
                        )
                    )
                    last_progress = monotonic_now

            gaps = await self.candles.find_missing_ranges_in_range(
                options.exchange_id,
                options.market_type,
                symbol,
                timeframe,
                start_time=earliest,
                end_time=end or now_ms(),
                max_ranges=100,
            )
            initial_gap_count = len(gaps)
            if options.repair_gaps and gaps:
                for start, stop in gaps:
                    await self.sync.repair_range(
                        exchange_id=options.exchange_id,
                        market_type=options.market_type,
                        symbol=symbol,
                        timeframe=timeframe,
                        from_time=start,
                        to_time=stop,
                        exchange=exchange,
                    )
                gaps = await self.candles.find_missing_ranges_in_range(
                    options.exchange_id,
                    options.market_type,
                    symbol,
                    timeframe,
                    start_time=earliest,
                    end_time=end or now_ms(),
                    max_ranges=100,
                )
            await self.states.replace_gaps(
                options.exchange_id, options.market_type, symbol, timeframe, gaps
            )
            state.gap_count = len(gaps)
            repaired = initial_gap_count - len(gaps)
            state.status = BackfillStatus.PARTIAL if gaps else BackfillStatus.COMPLETED
            state.completed_at = now_ms()
            state.last_error = None
            await self.states.save_state(state)
            return TargetResult(
                symbol,
                timeframe,
                state.status,
                pages=state.pages_downloaded,
                candles=state.candles_upserted,
                earliest=state.earliest_available_time,
                latest=state.latest_available_time,
                gaps=len(gaps),
                repaired_gaps=repaired,
            )
        except asyncio.CancelledError:
            state.status = BackfillStatus.INTERRUPTED
            state.last_error = "Interruption utilisateur"
            await self.states.save_state(state)
            raise
        except Exception as exc:
            state.status = BackfillStatus.FAILED
            state.last_error = f"{type(exc).__name__}: {exc}"
            state.completed_at = now_ms()
            await self.states.save_state(state)
            logger.exception("Échec backfill %s %s", symbol, timeframe)
            return TargetResult(
                symbol,
                timeframe,
                state.status,
                pages=state.pages_downloaded,
                candles=state.candles_upserted,
                error=state.last_error,
            )

    async def find_earliest(
        self,
        exchange: Any,
        options: BackfillOptions,
        symbol: str,
        timeframe: str,
    ) -> int | None:
        """Recherche la première bougie avec ``since=0`` et un repli borné."""
        rows = await self.sync.fetch_page(
            exchange,
            symbol,
            timeframe,
            0,
            options.page_limit,
            options.max_retries,
            options.retry_delay_seconds,
        )
        if not rows:
            return None
        candles = self.sync.normalize_page(
            rows,
            exchange_id=options.exchange_id,
            market_type=options.market_type,
            symbol=symbol,
            timeframe=timeframe,
        )
        earliest = candles[0].open_time
        interval = timeframe_milliseconds(timeframe)
        for _ in range(16):
            probe = max(0, earliest - options.page_limit * interval)
            if probe == 0:
                break
            older_rows = await self.sync.fetch_page(
                exchange,
                symbol,
                timeframe,
                probe,
                options.page_limit,
                options.max_retries,
                options.retry_delay_seconds,
            )
            if not older_rows:
                break
            older = self.sync.normalize_page(
                older_rows,
                exchange_id=options.exchange_id,
                market_type=options.market_type,
                symbol=symbol,
                timeframe=timeframe,
            )[0].open_time
            if older >= earliest:
                break
            earliest = older
        return earliest

    async def _finish_run(
        self,
        run_id: str,
        results: list[TargetResult],
        status: BackfillStatus,
    ) -> None:
        await self.states.finish_run(
            run_id,
            status,
            completed=sum(item.status is BackfillStatus.COMPLETED for item in results),
            partial=sum(item.status is BackfillStatus.PARTIAL for item in results),
            failed=sum(item.status is BackfillStatus.FAILED for item in results),
            interrupted=sum(item.status is BackfillStatus.INTERRUPTED for item in results),
            pages=sum(item.pages for item in results),
            candles=sum(item.candles for item in results),
        )
