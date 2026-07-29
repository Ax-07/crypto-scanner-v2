"""Orchestration non bloquante des recherches bornées de phase 4."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.experiments import dataset_fingerprint, evaluate_candidates
from app.models.backtest import BacktestStatus
from app.models.experiment import ExperimentConfig, ExperimentManifest
from app.models.experiment import ProfileStatus, SignalProfileVersion
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.experiment_repository import ExperimentRepository


class ExperimentManager:
    def __init__(self, repository: ExperimentRepository, backtests: BacktestRepository) -> None:
        self.repository = repository
        self.backtests = backtests
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._semaphore = asyncio.Semaphore(1)

    async def create(self, config: ExperimentConfig) -> ExperimentManifest:
        source = await self.backtests.get_job(config.source_backtest_id)
        if source is None or source.status != BacktestStatus.COMPLETED:
            raise ValueError("le backtest source doit exister et être terminé")
        observations = await self.backtests.all_observations(config.source_backtest_id)
        if any(item.snapshot_status != "confirmed" for item in observations):
            raise ValueError("la sélection de profils exige des observations confirmed")
        fingerprint = dataset_fingerprint(observations)
        manifest = ExperimentManifest(
            id=uuid4().hex,
            config=config,
            dataset_version=fingerprint,
            code_version="workspace-phase4",
            candidate_count=len(config.candidates),
            total_trials=len(config.candidates),
            search_space={
                "candidate_ids": [item.id for item in config.candidates],
                "linked_experiments": config.linked_experiment_ids,
                "seed": config.seed,
            },
        )
        await self.repository.save_manifest(manifest)
        self._tasks[manifest.id] = asyncio.create_task(self._run(manifest))
        return manifest

    async def _run(self, manifest: ExperimentManifest) -> None:
        async with self._semaphore:
            await self._run_limited(manifest)

    async def _run_limited(self, manifest: ExperimentManifest) -> None:
        manifest.status = BacktestStatus.RUNNING
        await self.repository.save_manifest(manifest)
        try:
            observations, outcomes = await asyncio.gather(
                self.backtests.all_observations(manifest.config.source_backtest_id),
                self.backtests.all_outcomes(manifest.config.source_backtest_id),
            )
            results, windows = await asyncio.to_thread(
                evaluate_candidates, manifest.config, observations, outcomes
            )
            manifest.results = results
            manifest.splits = windows
            manifest.status = BacktestStatus.COMPLETED
            source = await self.backtests.get_job(manifest.config.source_backtest_id)
            if source is not None:
                specs = {item.id: item for item in manifest.config.candidates}
                for result in results:
                    if not result.selected or result.candidate_id == "baseline-v1":
                        continue
                    if await self.repository.get_profile(result.candidate_id):
                        continue
                    spec = specs[result.candidate_id]
                    update: dict[str, object] = {}
                    if spec.weights:
                        update["confluence_weights"] = spec.weights
                    if spec.rsi_threshold is not None:
                        update["rsi_threshold"] = spec.rsi_threshold
                    if spec.min_confluence_score is not None:
                        update["min_confluence_score"] = spec.min_confluence_score
                    signal_config = source.config.signal_config.model_copy(update=update)
                    await self.repository.save_profile(
                        SignalProfileVersion(
                            id=result.candidate_id,
                            name=result.candidate_id,
                            version=f"1.0.0-{manifest.id[:8]}",
                            parent_id="baseline-v1",
                            description=spec.description or f"Candidat {spec.family}",
                            signal_config=signal_config,
                            experiment_id=manifest.id,
                            dataset_version=manifest.dataset_version,
                            code_version=manifest.code_version,
                            status=ProfileStatus.CANDIDATE,
                        )
                    )
            if len(manifest.config.candidates) >= 20:
                manifest.warnings.append(
                    "Comparaisons multiples: interpréter les rangs avec prudence; "
                    "les intervalles bootstrap par blocs sont requis avant promotion."
                )
        except asyncio.CancelledError:
            manifest.status = BacktestStatus.CANCELLED
        except Exception as exc:
            manifest.status = BacktestStatus.FAILED
            manifest.error = str(exc)
        finally:
            manifest.completed_at = datetime.now(timezone.utc)
            await self.repository.save_manifest(manifest)

    async def get(self, experiment_id: str) -> ExperimentManifest | None:
        return await self.repository.get_manifest(experiment_id)

    async def cancel_or_delete(self, experiment_id: str) -> ExperimentManifest | None:
        manifest = await self.get(experiment_id)
        if manifest is None:
            return None
        task = self._tasks.get(experiment_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return await self.get(experiment_id)
        await self.repository.delete_manifest(experiment_id)
        return manifest
