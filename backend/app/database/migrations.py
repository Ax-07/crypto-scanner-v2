"""Application idempotente des migrations SQLite internes."""

from __future__ import annotations

import logging

import aiosqlite

from app.database.schema import MIGRATIONS, SCHEMA_VERSION

logger = logging.getLogger(__name__)


async def apply_migrations(connection: aiosqlite.Connection) -> None:
    """Crée la table de versions puis applique chaque migration manquante."""
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
        """)
    cursor = await connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
    row = await cursor.fetchone()
    current = int(row[0]) if row else 0
    for version in range(current + 1, SCHEMA_VERSION + 1):
        script = MIGRATIONS[version]
        await connection.executescript(script)
        await connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) "
            "VALUES (?, CAST(strftime('%s', 'now') AS INTEGER) * 1000)",
            (version,),
        )
        logger.info("Migration SQLite %s appliquée", version)
    await connection.commit()
