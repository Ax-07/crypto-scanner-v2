"""Gestion de connexions SQLite courtes et configurées uniformément."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from app.database.migrations import apply_migrations

logger = logging.getLogger(__name__)


class Database:
    """Fabrique testable de connexions ``aiosqlite`` vers un fichier unique."""

    def __init__(self, path: Path) -> None:
        """Mémorise le chemin sans ouvrir de transaction globale."""
        self.path = Path(path)
        self._initialized = False

    async def initialize(self) -> None:
        """Crée le dossier, active WAL et applique les migrations."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connection() as connection:
            cursor = await connection.execute("PRAGMA journal_mode = WAL")
            mode = await cursor.fetchone()
            await apply_migrations(connection)
            if not mode or str(mode[0]).lower() != "wal":
                logger.warning("SQLite n'a pas activé WAL (mode=%s)", mode[0] if mode else None)
        self._initialized = True
        logger.info("Stockage SQLite initialisé")

    async def close(self) -> None:
        """Termine le cycle de vie; aucune connexion longue n'est conservée."""
        self._initialized = False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Ouvre une connexion configurée, puis la ferme systématiquement."""
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        try:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA synchronous = NORMAL")
            await connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
        finally:
            await connection.close()
