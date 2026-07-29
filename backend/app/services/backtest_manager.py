"""Cycle de vie persistant, annulable et observable des backtests."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.models.backtest import BacktestConfig, BacktestJob, BacktestStatus
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_engine import BacktestEngine, SQLiteHistoricalRepository

logger = logging.getLogger(__name__)


class BacktestManager:
    def __init__(self, repository: BacktestRepository, candles: CandleRepository) -> None:
        self.repository = repository
        self.engine = BacktestEngine(SQLiteHistoricalRepository(candles), repository)
        self._jobs: dict[str, BacktestJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._versions: dict[str, int] = {}

    async def initialize(self) -> None:
        await self.repository.recover_interrupted()

    async def create_job(self, config: BacktestConfig) -> BacktestJob:
        job = BacktestJob(id=uuid4().hex, config=config)
        self._jobs[job.id] = job
        self._conditions[job.id] = asyncio.Condition()
        self._versions[job.id] = 0
        await self.repository.save_job(job)
        self._tasks[job.id] = asyncio.create_task(self._run(job))
        return job

    async def resume(self, job_id: str) -> BacktestJob | None:
        """Reprend explicitement un job depuis son dernier checkpoint durable."""
        job = await self.get_job(job_id)
        if job is None:
            return None
        if job.status not in {
            BacktestStatus.INTERRUPTED,
            BacktestStatus.CANCELLED,
            BacktestStatus.FAILED,
        }:
            raise ValueError("seul un backtest interrompu, annulé ou échoué peut être repris")
        checkpoint = await self.repository.get_checkpoint(job_id)
        if checkpoint is None:
            raise ValueError("aucun checkpoint durable disponible")
        job.checkpoint = checkpoint
        job.status = BacktestStatus.PENDING
        job.error = None
        job.completed_at = None
        self._jobs[job.id] = job
        self._conditions.setdefault(job.id, asyncio.Condition())
        self._versions.setdefault(job.id, 0)
        await self.repository.save_job(job)
        self._tasks[job.id] = asyncio.create_task(self._run(job))
        return job

    async def get_job(self, job_id: str) -> BacktestJob | None:
        return self._jobs.get(job_id) or await self.repository.get_job(job_id)

    async def _publish(self, job: BacktestJob) -> None:
        await self.repository.save_job(job)
        condition = self._conditions.get(job.id)
        if condition:
            async with condition:
                self._versions[job.id] = self._versions.get(job.id, 0) + 1
                condition.notify_all()

    async def wait_for_change(self, job_id: str, version: int) -> tuple[int, BacktestJob] | None:
        condition = self._conditions.get(job_id)
        if condition is None:
            job = await self.get_job(job_id)
            return (0, job) if job else None
        async with condition:
            await condition.wait_for(lambda: self._versions.get(job_id, -1) != version)
        job = await self.get_job(job_id)
        return (self._versions.get(job_id, version), job) if job else None

    def current_version(self, job_id: str) -> int:
        return self._versions.get(job_id, 0)

    async def cancel(self, job_id: str) -> BacktestJob | None:
        job = await self.get_job(job_id)
        task = self._tasks.get(job_id)
        if job is None:
            return None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return await self.get_job(job_id)

    async def delete(self, job_id: str) -> bool:
        job = await self.get_job(job_id)
        if job is None:
            return False
        if job.status in {BacktestStatus.PENDING, BacktestStatus.RUNNING}:
            await self.cancel(job_id)
        self._jobs.pop(job_id, None)
        self._tasks.pop(job_id, None)
        self._conditions.pop(job_id, None)
        self._versions.pop(job_id, None)
        return await self.repository.delete_job(job_id)

    async def _run(self, job: BacktestJob) -> None:
        job.status = BacktestStatus.RUNNING
        job.started_at = job.started_at or datetime.now(timezone.utc)
        await self._publish(job)
        try:
            await self.engine.run(job, lambda progress: self._progress(job, progress))
            job.status = BacktestStatus.COMPLETED
        except asyncio.CancelledError:
            job.status = BacktestStatus.CANCELLED
            job.progress.phase = "cancelled"
            logger.info("Backtest %s annulé", job.id)
        except Exception as exc:
            job.status = BacktestStatus.FAILED
            job.error = str(exc)
            job.progress.phase = "failed"
            logger.exception("Échec du backtest %s", job.id)
        finally:
            job.completed_at = datetime.now(timezone.utc)
            await self._publish(job)

    async def _progress(self, job: BacktestJob, progress) -> None:
        job.progress = progress
        await self._publish(job)
