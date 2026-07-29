"""Persistance reproductible des expériences, profils et décisions."""

from __future__ import annotations

from datetime import datetime, timezone

from app.database.connection import Database
from app.models.experiment import (
    ExperimentManifest,
    ProfileStatus,
    PromotionDecision,
    ShadowComparison,
    SignalProfileVersion,
)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


class ExperimentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def save_manifest(self, manifest: ExperimentManifest) -> None:
        now = _ms(datetime.now(timezone.utc))
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO experiment_jobs(id, status, manifest_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                    manifest_json=excluded.manifest_json, updated_at=excluded.updated_at
                """,
                (
                    manifest.id,
                    manifest.status.value,
                    manifest.model_dump_json(),
                    _ms(manifest.created_at),
                    now,
                ),
            )
            await connection.commit()

    async def get_manifest(self, experiment_id: str) -> ExperimentManifest | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT manifest_json FROM experiment_jobs WHERE id=?", (experiment_id,)
            )
            row = await cursor.fetchone()
        return ExperimentManifest.model_validate_json(row[0]) if row else None

    async def delete_manifest(self, experiment_id: str) -> bool:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "DELETE FROM experiment_jobs WHERE id=?", (experiment_id,)
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def save_profile(self, profile: SignalProfileVersion) -> None:
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO signal_profiles(id, version, status, profile_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.version,
                    profile.status.value,
                    profile.model_dump_json(),
                    _ms(profile.created_at),
                ),
            )
            await connection.execute(
                """
                INSERT INTO signal_profile_lifecycle(
                    profile_id, from_status, to_status, decision, comment, origin, changed_at
                ) VALUES (?, NULL, ?, 'created', ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.status.value,
                    profile.description,
                    profile.origin,
                    _ms(profile.created_at),
                ),
            )
            await connection.commit()

    async def profiles(self) -> list[SignalProfileVersion]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT profile_json, status FROM signal_profiles ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
        return [
            SignalProfileVersion.model_validate_json(row[0]).model_copy(
                update={"status": ProfileStatus(row[1])}
            )
            for row in rows
        ]

    async def get_profile(self, profile_id: str) -> SignalProfileVersion | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT profile_json, status FROM signal_profiles WHERE id=?", (profile_id,)
            )
            row = await cursor.fetchone()
        return (
            SignalProfileVersion.model_validate_json(row[0]).model_copy(
                update={"status": ProfileStatus(row[1])}
            )
            if row
            else None
        )

    async def set_profile_status(
        self,
        profile_id: str,
        status: str,
        *,
        decision: str = "status_change",
        comment: str = "",
        origin: str = "api",
    ) -> bool:
        async with self.database.connection() as connection:
            current_cursor = await connection.execute(
                "SELECT status FROM signal_profiles WHERE id=?", (profile_id,)
            )
            current = await current_cursor.fetchone()
            if current is None:
                return False
            if current[0] == status:
                return True
            cursor = await connection.execute(
                "UPDATE signal_profiles SET status=? WHERE id=?",
                (status, profile_id),
            )
            await connection.execute(
                """
                INSERT INTO signal_profile_lifecycle(
                    profile_id, from_status, to_status, decision, comment, origin, changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    current[0],
                    status,
                    decision,
                    comment,
                    origin,
                    _ms(datetime.now(timezone.utc)),
                ),
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def save_decision(self, decision: PromotionDecision) -> None:
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO promotion_decisions(
                    profile_id, experiment_id, approved, decision_json, decided_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    decision.profile_id,
                    decision.experiment_id,
                    int(decision.approved),
                    decision.model_dump_json(),
                    _ms(decision.decided_at),
                ),
            )
            if decision.approved:
                cursor = await connection.execute(
                    "SELECT id, status FROM signal_profiles "
                    "WHERE (status='production' AND id<>?) OR id=?",
                    (decision.profile_id, decision.profile_id),
                )
                transitions = await cursor.fetchall()
                for row in transitions:
                    target = (
                        ProfileStatus.PRODUCTION.value
                        if row["id"] == decision.profile_id
                        else ProfileStatus.RETIRED.value
                    )
                    if row["status"] == target:
                        continue
                    await connection.execute(
                        "UPDATE signal_profiles SET status=? WHERE id=?",
                        (target, row["id"]),
                    )
                    await connection.execute(
                        """
                        INSERT INTO signal_profile_lifecycle(
                            profile_id, from_status, to_status, decision,
                            comment, origin, changed_at
                        ) VALUES (?, ?, ?, 'promotion', ?, 'human', ?)
                        """,
                        (
                            row["id"],
                            row["status"],
                            target,
                            decision.comment,
                            _ms(decision.decided_at),
                        ),
                    )
            await connection.commit()

    async def lifecycle(self, profile_id: str) -> list[dict[str, object]]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT from_status, to_status, decision, comment, origin, changed_at
                FROM signal_profile_lifecycle
                WHERE profile_id=?
                ORDER BY changed_at, id
                """,
                (profile_id,),
            )
            rows = await cursor.fetchall()
        return [
            {
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "decision": row["decision"],
                "comment": row["comment"],
                "origin": row["origin"],
                "changed_at": datetime.fromtimestamp(row["changed_at"] / 1_000, tz=timezone.utc),
            }
            for row in rows
        ]

    async def add_shadow(self, comparison: ShadowComparison) -> int:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO shadow_comparisons(
                    symbol, timeframe, timestamp, production_profile_id,
                    candidate_profile_id, comparison_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    symbol, timeframe, timestamp, production_profile_id, candidate_profile_id
                ) DO UPDATE SET comparison_json=excluded.comparison_json
                """,
                (
                    comparison.symbol,
                    comparison.timeframe,
                    _ms(comparison.timestamp),
                    comparison.production_profile_id,
                    comparison.candidate_profile_id,
                    comparison.model_dump_json(),
                ),
            )
            lookup = await connection.execute(
                """
                SELECT id FROM shadow_comparisons
                WHERE symbol=? AND timeframe=? AND timestamp=?
                  AND production_profile_id=? AND candidate_profile_id=?
                """,
                (
                    comparison.symbol,
                    comparison.timeframe,
                    _ms(comparison.timestamp),
                    comparison.production_profile_id,
                    comparison.candidate_profile_id,
                ),
            )
            row = await lookup.fetchone()
            await connection.commit()
            return int(row[0]) if row else int(cursor.lastrowid or 0)

    async def shadows(
        self, *, offset: int = 0, limit: int = 100, symbol: str | None = None
    ) -> tuple[list[ShadowComparison], int]:
        where, params = ("WHERE symbol=?", [symbol.upper()]) if symbol else ("", [])
        async with self.database.connection() as connection:
            count = await connection.execute(
                f"SELECT COUNT(*) FROM shadow_comparisons {where}", params
            )
            count_row = await count.fetchone()
            cursor = await connection.execute(
                f"SELECT comparison_json FROM shadow_comparisons {where} "
                "ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            rows = await cursor.fetchall()
        return (
            [ShadowComparison.model_validate_json(row[0]) for row in rows],
            int(count_row[0]) if count_row else 0,
        )
