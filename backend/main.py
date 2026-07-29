"""Point d'entrée ASGI stable pour Uvicorn et les commandes historiques."""

from app.main import app

__all__ = ["app"]
