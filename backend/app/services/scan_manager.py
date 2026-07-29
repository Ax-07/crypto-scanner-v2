"""Gère en mémoire le cycle de vie et la publication des jobs de scan.

Le manager planifie les tâches, publie leurs changements et gère l'annulation.
La logique d'analyse technique appartient à ``ScannerService``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.settings import ScanConfig
from app.core.config import AppSettings, get_app_settings
from app.models.scanner import ScanJob, ScanProgress, ScanStatus
from app.services.scanner import ScannerService

logger = logging.getLogger(__name__)


class ScanManager:
    """Registre mono-processus des jobs, tâches et conditions de notification."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        """Crée un registre vide avec les règles de rétention fournies."""
        self.settings = settings or get_app_settings()
        self._jobs: dict[str, ScanJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._versions: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, config: ScanConfig) -> ScanJob:
        """Enregistre un job puis planifie immédiatement son exécution.

        La purge des anciens jobs terminés a lieu sous verrou avant l'insertion.
        Le job est accessible aux routes dès le retour de cette coroutine.
        """
        job = ScanJob(id=uuid4().hex, config=config)
        async with self._lock:
            self._purge_completed_locked()
            self._jobs[job.id] = job
            self._conditions[job.id] = asyncio.Condition()
            self._versions[job.id] = 0
            self._tasks[job.id] = asyncio.create_task(self._run_job(job.id))
        return job

    def get_job(self, job_id: str) -> ScanJob | None:
        """Retourne le job en mémoire, ou ``None`` s'il est absent ou purgé."""
        return self._jobs.get(job_id)

    def current_version(self, job_id: str) -> int:
        """Retourne la version de publication courante, zéro par défaut."""
        return self._versions.get(job_id, 0)

    async def wait_for_change(self, job_id: str, version: int) -> tuple[int, dict] | None:
        """Attend sans polling qu'un job publie une version différente.

        Returns:
            Nouvelle version et payload, ou ``None`` si le job n'est plus suivi.
        """
        condition = self._conditions.get(job_id)
        if condition is None:
            return None
        async with condition:
            await condition.wait_for(lambda: self._versions.get(job_id, -1) != version)
        job = self._jobs.get(job_id)
        return (self._versions.get(job_id, version), job.public_payload()) if job else None

    async def _publish(self, job_id: str) -> None:
        """Incrémente la version d'un job et réveille tous ses abonnés."""
        condition = self._conditions.get(job_id)
        if condition is None:
            return
        async with condition:
            self._versions[job_id] = self._versions.get(job_id, 0) + 1
            condition.notify_all()

    def _purge_completed_locked(self) -> None:
        """Retire les jobs terminés expirés ou excédentaires et leurs références.

        Cette méthode suppose ``_lock`` acquis et n'est appelée qu'à la création
        d'un job. Les jobs actifs ne sont jamais candidats à la purge.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.settings.completed_job_ttl_seconds)
        finished = sorted(
            (job for job in self._jobs.values() if job.completed_at is not None),
            key=lambda job: job.completed_at or now,
        )
        remove = {job.id for job in finished if job.completed_at and job.completed_at < cutoff}
        excess = max(0, len(self._jobs) - self.settings.max_retained_jobs + 1)
        remove.update(job.id for job in finished[:excess])
        for job_id in remove:
            self._jobs.pop(job_id, None)
            self._conditions.pop(job_id, None)
            self._versions.pop(job_id, None)
            self._tasks.pop(job_id, None)

    async def cancel_job(self, job_id: str) -> ScanJob | None:
        """Annule et attend la tâche active tout en conservant les résultats partiels."""
        job = self._jobs.get(job_id)
        task = self._tasks.get(job_id)
        if job is None:
            return None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # Possible lorsque le job est annulé avant même son démarrage.
                job.status = ScanStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)
        return job

    async def _run_job(self, job_id: str) -> None:
        """Fait évoluer un job de ``running`` vers son état final et publie chaque étape."""
        job = self._jobs[job_id]
        job.status = ScanStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await self._publish(job_id)

        async def update_progress(progress: ScanProgress) -> None:
            """Remplace le snapshot de progression et avertit les abonnés."""
            job.progress = progress
            await self._publish(job_id)

        scanner: ScannerService | None = None
        try:
            scanner = ScannerService(job.config)
            job.results = await scanner.scan(update_progress)
            job.status = ScanStatus.COMPLETED
        except asyncio.CancelledError:
            if scanner is not None:
                job.results = list(getattr(scanner, "partial_results", job.results))
            job.status = ScanStatus.CANCELLED
            logger.info("Scan %s annulé", job.id)
        except Exception as exc:
            job.status = ScanStatus.FAILED
            job.error = str(exc)
            logger.exception("Échec du scan %s", job.id)
        finally:
            job.completed_at = datetime.now(timezone.utc)
            await self._publish(job_id)


scan_manager = ScanManager()
