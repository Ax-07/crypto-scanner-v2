"""Persistance SQLite séparée des jobs et résultats de backtest."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.database.connection import Database
from app.models.backtest import (
    BacktestJob,
    BacktestStatus,
    ForwardOutcome,
    SignalObservation,
)


def _ms(value: datetime | None) -> int | None:
    return int(value.timestamp() * 1_000) if value else None


def _dt(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value / 1_000, tz=timezone.utc) if value is not None else None


class BacktestRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def save_job(self, job: BacktestJob) -> None:
        now = int(datetime.now(timezone.utc).timestamp() * 1_000)
        config_exclude = (
            {"portfolio_simulation"} if job.config.portfolio_simulation is None else None
        )
        summary_exclude = (
            {"portfolio_simulation"}
            if job.summary is not None and job.summary.portfolio_simulation is None
            else None
        )
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO backtest_jobs (
                    id, status, config_json, progress_json, summary_json,
                    correlations_json, ablations_json, warnings_json, error,
                    created_at, started_at, completed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status, progress_json=excluded.progress_json,
                    summary_json=excluded.summary_json,
                    correlations_json=excluded.correlations_json,
                    ablations_json=excluded.ablations_json,
                    warnings_json=excluded.warnings_json, error=excluded.error,
                    started_at=excluded.started_at, completed_at=excluded.completed_at,
                    updated_at=excluded.updated_at
                """,
                (
                    job.id,
                    job.status.value,
                    job.config.model_dump_json(exclude=config_exclude),
                    job.progress.model_dump_json(),
                    (job.summary.model_dump_json(exclude=summary_exclude) if job.summary else None),
                    json.dumps(job.correlations, allow_nan=False) if job.correlations else None,
                    json.dumps(job.ablations, allow_nan=False) if job.ablations else None,
                    json.dumps(job.warnings),
                    job.error,
                    _ms(job.created_at),
                    _ms(job.started_at),
                    _ms(job.completed_at),
                    now,
                ),
            )
            await connection.commit()

    async def get_job(self, job_id: str) -> BacktestJob | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute("SELECT * FROM backtest_jobs WHERE id=?", (job_id,))
            row = await cursor.fetchone()
        if row is None:
            return None
        checkpoint = await self.get_checkpoint(row["id"])
        return BacktestJob(
            id=row["id"],
            status=row["status"],
            config=json.loads(row["config_json"]),
            progress=json.loads(row["progress_json"]),
            summary=json.loads(row["summary_json"]) if row["summary_json"] else None,
            correlations=(
                json.loads(row["correlations_json"]) if row["correlations_json"] else None
            ),
            ablations=json.loads(row["ablations_json"]) if row["ablations_json"] else None,
            warnings=json.loads(row["warnings_json"]),
            error=row["error"],
            created_at=_dt(row["created_at"]) or datetime.now(timezone.utc),
            started_at=_dt(row["started_at"]),
            completed_at=_dt(row["completed_at"]),
            dataset_version=(
                str(checkpoint.get("dataset_version", "unknown")) if checkpoint else "unknown"
            ),
            algorithm_version=(
                str(checkpoint.get("algorithm_version", "signal-evaluation-v2"))
                if checkpoint
                else "signal-evaluation-v2"
            ),
            checkpoint=checkpoint,
            config_fingerprint=(
                str(checkpoint["config_fingerprint"])
                if checkpoint and checkpoint.get("config_fingerprint")
                else None
            ),
        )

    async def list_jobs(
        self, *, offset: int = 0, limit: int = 100
    ) -> tuple[list[BacktestJob], int]:
        async with self.database.connection() as connection:
            count_cursor = await connection.execute("SELECT COUNT(*) FROM backtest_jobs")
            count_row = await count_cursor.fetchone()
            cursor = await connection.execute(
                "SELECT id FROM backtest_jobs ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
        jobs = [job for row in rows if (job := await self.get_job(row["id"])) is not None]
        return jobs, int(count_row[0]) if count_row else 0

    async def recover_interrupted(self) -> int:
        """Marque les exécutions abandonnées comme explicitement reprenables."""
        now = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                UPDATE backtest_jobs
                SET status=?, error=COALESCE(error, ?), completed_at=?, updated_at=?
                WHERE status IN (?, ?)
                """,
                (
                    BacktestStatus.INTERRUPTED.value,
                    "Exécution interrompue par le redémarrage du service",
                    now,
                    now,
                    BacktestStatus.PENDING.value,
                    BacktestStatus.RUNNING.value,
                ),
            )
            await connection.commit()
            return cursor.rowcount

    async def save_checkpoint(self, job_id: str, checkpoint: dict[str, Any]) -> None:
        """Persiste un curseur de replay idempotent."""
        now = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO backtest_checkpoints (
                    job_id, symbol_index, symbol, decision_index, processed,
                    observations, algorithm_version, dataset_version, status,
                    checkpoint_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    symbol_index=excluded.symbol_index, symbol=excluded.symbol,
                    decision_index=excluded.decision_index, processed=excluded.processed,
                    observations=excluded.observations,
                    algorithm_version=excluded.algorithm_version,
                    dataset_version=excluded.dataset_version, status=excluded.status,
                    checkpoint_json=excluded.checkpoint_json, updated_at=excluded.updated_at
                """,
                (
                    job_id,
                    int(checkpoint.get("symbol_index", 0)),
                    checkpoint.get("symbol"),
                    int(checkpoint.get("decision_index", -1)),
                    int(checkpoint.get("processed", 0)),
                    int(checkpoint.get("observations", 0)),
                    str(checkpoint.get("algorithm_version", "signal-evaluation-v2")),
                    str(checkpoint.get("dataset_version", "unknown")),
                    str(checkpoint.get("status", "running")),
                    json.dumps(checkpoint, allow_nan=False),
                    now,
                ),
            )
            await connection.commit()

    async def get_checkpoint(self, job_id: str) -> dict[str, Any] | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT checkpoint_json FROM backtest_checkpoints WHERE job_id=?", (job_id,)
            )
            row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def save_artifact(self, job_id: str, kind: str, payload: Any) -> None:
        """Persiste un résultat analytique adressable sans gonfler le job."""
        now = int(datetime.now(timezone.utc).timestamp() * 1_000)
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO backtest_artifacts(job_id, kind, artifact_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id, kind) DO UPDATE SET
                    artifact_json=excluded.artifact_json, updated_at=excluded.updated_at
                """,
                (job_id, kind, json.dumps(payload, allow_nan=False), now),
            )
            await connection.commit()

    async def get_artifact(self, job_id: str, kind: str) -> Any | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT artifact_json FROM backtest_artifacts WHERE job_id=? AND kind=?",
                (job_id, kind),
            )
            row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def delete_job(self, job_id: str) -> bool:
        async with self.database.connection() as connection:
            cursor = await connection.execute("DELETE FROM backtest_jobs WHERE id=?", (job_id,))
            await connection.commit()
            return cursor.rowcount > 0

    async def add_observation(self, observation: SignalObservation) -> int:
        payload = observation.model_dump(mode="json", exclude={"id"})
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO backtest_observations (
                    job_id, symbol, decision_time, snapshot_status, accepted,
                    rejection_stage, rejection_reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, symbol, decision_time, snapshot_status) DO UPDATE SET
                    accepted=excluded.accepted,
                    rejection_stage=excluded.rejection_stage,
                    rejection_reason=excluded.rejection_reason,
                    payload_json=excluded.payload_json
                """,
                (
                    observation.job_id,
                    observation.symbol,
                    _ms(observation.decision_time),
                    observation.snapshot_status,
                    int(observation.accepted),
                    observation.rejection_stage,
                    observation.rejection_reason,
                    json.dumps(payload, allow_nan=False),
                ),
            )
            cursor = await connection.execute(
                """
                SELECT id FROM backtest_observations
                WHERE job_id=? AND symbol=? AND decision_time=? AND snapshot_status=?
                """,
                (
                    observation.job_id,
                    observation.symbol,
                    _ms(observation.decision_time),
                    observation.snapshot_status,
                ),
            )
            row = await cursor.fetchone()
            await connection.commit()
            return int(row[0]) if row else 0

    async def add_outcomes(
        self, job_id: str, observation_id: int, outcomes: list[ForwardOutcome]
    ) -> None:
        if not outcomes:
            return
        rows = []
        for outcome in outcomes:
            item = outcome.model_copy(update={"observation_id": observation_id})
            rows.append(
                (
                    job_id,
                    observation_id,
                    item.horizon,
                    item.model_dump_json(),
                )
            )
        async with self.database.connection() as connection:
            await connection.executemany(
                """
                INSERT INTO backtest_outcomes (
                    job_id, observation_id, horizon, payload_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(observation_id, horizon) DO UPDATE SET
                    job_id=excluded.job_id, payload_json=excluded.payload_json
                """,
                rows,
            )
            await connection.commit()

    async def observations(
        self,
        job_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        accepted: bool | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        grade: str | None = None,
        rejection_stage: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        has_divergence: bool | None = None,
        sort_by: str = "decision_time",
        order: str = "asc",
    ) -> tuple[list[SignalObservation], int]:
        clauses = ["job_id=?"]
        params: list[Any] = [job_id]
        if accepted is not None:
            clauses.append("accepted=?")
            params.append(int(accepted))
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        if timeframe:
            clauses.append("json_extract(payload_json, '$.timeframe')=?")
            params.append(timeframe)
        if start_ms is not None:
            clauses.append("decision_time>=?")
            params.append(start_ms)
        if end_ms is not None:
            clauses.append("decision_time<=?")
            params.append(end_ms)
        if grade:
            clauses.append("json_extract(payload_json, '$.confluence_grade')=?")
            params.append(grade.upper())
        if rejection_stage:
            clauses.append("rejection_stage=?")
            params.append(rejection_stage)
        if min_score is not None:
            clauses.append("json_extract(payload_json, '$.confluence_score')>=?")
            params.append(min_score)
        if max_score is not None:
            clauses.append("json_extract(payload_json, '$.confluence_score')<=?")
            params.append(max_score)
        if has_divergence is not None:
            clauses.append(
                "COALESCE(json_array_length(json_extract(payload_json, '$.divergences')), 0) "
                + ("> 0" if has_divergence else "= 0")
            )
        where = " AND ".join(clauses)
        sort_column = {
            "decision_time": "decision_time",
            "symbol": "symbol",
            "accepted": "accepted",
            "confluence_score": "json_extract(payload_json, '$.confluence_score')",
        }.get(sort_by, "decision_time")
        direction = "DESC" if order.lower() == "desc" else "ASC"
        async with self.database.connection() as connection:
            count_cursor = await connection.execute(
                f"SELECT COUNT(*) FROM backtest_observations WHERE {where}", tuple(params)
            )
            count_row = await count_cursor.fetchone()
            cursor = await connection.execute(
                f"""
                SELECT id, payload_json FROM backtest_observations
                WHERE {where} ORDER BY {sort_column} {direction}, id {direction}
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )
            rows = await cursor.fetchall()
        items = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["id"] = row["id"]
            items.append(SignalObservation.model_validate(payload))
        return items, int(count_row[0]) if count_row else 0

    async def ml_source_rows(
        self,
        job_id: str,
        *,
        horizon: int = 6,
        offset: int = 0,
        limit: int = 1_000,
    ) -> tuple[
        list[tuple[SignalObservation, ForwardOutcome]],
        int,
    ]:
        """Charge les couples observation/outcome destinés au dataset ML.

        La jointure est effectuée directement par SQLite. Seules les
        observations confirmées et l'horizon demandé sont chargés.
        """
        if horizon < 1:
            raise ValueError("horizon doit être supérieur ou égal à 1")

        if offset < 0:
            raise ValueError("offset doit être supérieur ou égal à 0")

        if limit < 1:
            raise ValueError("limit doit être supérieur ou égal à 1")

        query_parameters = (
            job_id,
            horizon,
        )

        async with self.database.connection() as connection:
            count_cursor = await connection.execute(
                """
                SELECT COUNT(*)
                FROM backtest_observations AS observation
                INNER JOIN backtest_outcomes AS outcome
                    ON outcome.observation_id = observation.id
                    AND outcome.job_id = observation.job_id
                WHERE observation.job_id = ?
                    AND observation.snapshot_status = 'confirmed'
                    AND outcome.horizon = ?
                """,
                query_parameters,
            )
            count_row = await count_cursor.fetchone()

            cursor = await connection.execute(
                """
                SELECT
                    observation.id AS observation_id,
                    observation.payload_json AS observation_payload_json,
                    outcome.payload_json AS outcome_payload_json
                FROM backtest_observations AS observation
                INNER JOIN backtest_outcomes AS outcome
                    ON outcome.observation_id = observation.id
                    AND outcome.job_id = observation.job_id
                WHERE observation.job_id = ?
                    AND observation.snapshot_status = 'confirmed'
                    AND outcome.horizon = ?
                ORDER BY
                    observation.decision_time ASC,
                    observation.id ASC
                LIMIT ? OFFSET ?
                """,
                (
                    *query_parameters,
                    limit,
                    offset,
                ),
            )
            rows = await cursor.fetchall()

        items: list[tuple[SignalObservation, ForwardOutcome]] = []

        for row in rows:
            observation_payload = json.loads(row["observation_payload_json"])
            observation_payload["id"] = row["observation_id"]

            outcome_payload = json.loads(row["outcome_payload_json"])
            outcome_payload["observation_id"] = row["observation_id"]

            observation = SignalObservation.model_validate(observation_payload)
            outcome = ForwardOutcome.model_validate(outcome_payload)

            items.append(
                (
                    observation,
                    outcome,
                )
            )

        total = int(count_row[0]) if count_row else 0
        return items, total

    async def all_observations(self, job_id: str) -> list[SignalObservation]:
        items, _ = await self.observations(job_id, limit=1_000_000)
        return items

    async def all_outcomes(self, job_id: str) -> list[ForwardOutcome]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT payload_json FROM backtest_outcomes
                WHERE job_id=? ORDER BY observation_id, horizon
                """,
                (job_id,),
            )
            rows = await cursor.fetchall()
        return [ForwardOutcome.model_validate_json(row["payload_json"]) for row in rows]
