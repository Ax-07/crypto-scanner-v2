"""Configure les journaux console et fichier du processus backend."""

from __future__ import annotations

import logging
import os
from pathlib import Path


def configure_logging() -> None:
    """Initialise le logging racine selon ``LOG_LEVEL`` et ``LOG_DIR``.

    Le dossier est créé si nécessaire et ``scanner.log`` est ouvert en UTF-8.
    L'option ``force`` garantit une configuration identique sous Uvicorn.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    handlers.append(logging.FileHandler(log_dir / "scanner.log", encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
