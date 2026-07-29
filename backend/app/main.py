"""Fabrique de l'application FastAPI et routage HTTP/WebSocket principal."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.scanner import router as scanner_router
from app.api.candles import router as candles_router
from app.api.history import router as history_router
from app.api.backtests import router as backtests_router
from app.api.experiments import router as experiments_router
from app.core.config import get_app_settings
from app.core.logging import configure_logging
from app.core.settings import MarketIndicatorConfig
from app.core.settings import ScanConfig
from app.database.connection import Database
from app.repositories.candle_repository import CandleRepository
from app.repositories.backfill_repository import BackfillRepository
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.experiment_repository import ExperimentRepository
from app.services.backtest_manager import BacktestManager
from app.services.experiment_manager import ExperimentManager
from app.models.experiment import ProfileStatus, SignalProfileVersion
from app.services.candle_sync import CandleSyncService
from app.services.market_history import MarketHistoryService
from app.services.shadow_evaluation import ShadowEvaluationService
from app.services.market_stream import DISPLAY_LIMIT, SYMBOL, TIMEFRAME, websocket_market_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise les journaux et le stockage local pendant le cycle FastAPI."""
    configure_logging()
    settings = get_app_settings()
    database = Database(settings.database_path)
    repository = CandleRepository(database)
    candle_sync = CandleSyncService(repository, settings)
    market_history = MarketHistoryService(repository, candle_sync)
    backfill_repository = BackfillRepository(database)
    if settings.candle_storage_enabled:
        await database.initialize()
    backtest_repository = BacktestRepository(database)
    backtest_manager = BacktestManager(backtest_repository, repository)
    experiment_repository = ExperimentRepository(database)
    experiment_manager = ExperimentManager(experiment_repository, backtest_repository)
    shadow_evaluation = ShadowEvaluationService(experiment_repository)
    if settings.candle_storage_enabled:
        await backtest_manager.initialize()
        if await experiment_repository.get_profile("baseline-v1") is None:
            await experiment_repository.save_profile(
                SignalProfileVersion(
                    id="baseline-v1",
                    name="Baseline canonique",
                    version="1.0.0",
                    description="Stratégie de production figée avant les recherches de phase 4.",
                    signal_config=ScanConfig(),
                    dataset_version="production-config",
                    code_version="workspace-phase4",
                    status=ProfileStatus.PRODUCTION,
                )
            )
    application.state.database = database
    application.state.settings = settings
    application.state.candle_repository = repository
    application.state.candle_sync = candle_sync
    application.state.market_history = market_history
    application.state.backfill_repository = backfill_repository
    application.state.backtest_repository = backtest_repository
    application.state.backtest_manager = backtest_manager
    application.state.experiment_repository = experiment_repository
    application.state.experiment_manager = experiment_manager
    application.state.shadow_evaluation = shadow_evaluation
    try:
        yield
    finally:
        await database.close()


def create_app() -> FastAPI:
    """Construit l'application, ses middlewares, routes et fallback React."""
    application = FastAPI(
        title="Crypto Scanner & Trading Dashboard",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(get_app_settings().cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(scanner_router)
    application.include_router(candles_router)
    application.include_router(history_router)
    application.include_router(backtests_router)
    application.include_router(experiments_router)

    @application.get(
        "/api/health",
        summary="Vérifier la santé de l'API",
        response_description="État minimal du backend",
    )
    async def api_health() -> dict[str, str]:
        """Retourne une sonde de santé minimale pour les clients API."""
        return {"status": "ok"}

    @application.get(
        "/health",
        summary="Vérifier la santé du flux marché",
        response_description="État et valeurs par défaut du flux marché",
    )
    async def health() -> JSONResponse:
        """Retourne la santé et les valeurs par défaut du flux marché."""
        return JSONResponse(
            {
                "status": "ok",
                "symbol": SYMBOL,
                "timeframe": TIMEFRAME,
                "display_limit": DISPLAY_LIMIT,
            }
        )

    @application.websocket("/ws")
    async def market_websocket(
        websocket: WebSocket,
        symbol: str = SYMBOL,
        timeframe: str = TIMEFRAME,
        include_history: bool = True,
        profile: str | None = None,
    ) -> None:
        """Délègue une connexion WebSocket au service de marché temps réel."""
        await websocket_market_data(
            websocket,
            symbol,
            timeframe,
            repository=application.state.candle_repository,
            candle_sync=application.state.candle_sync,
            include_history=include_history,
            profile=(
                MarketIndicatorConfig.model_validate_json(profile)
                if profile
                else MarketIndicatorConfig()
            ),
            shadow_evaluation=(
                application.state.shadow_evaluation
                if application.state.settings.shadow_mode_enabled
                else None
            ),
        )

    @application.get(
        "/",
        summary="Servir l'accueil React",
        response_description="Index React ou aide de compilation",
    )
    async def frontend_index():
        """Sert l'index React compilé ou une aide de démarrage avec statut 503."""
        index_file = FRONTEND_DIST / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(
            status_code=503,
            content={
                "message": "Le frontend React n'est pas encore compilé.",
                "development": "cd frontend && pnpm install && pnpm run dev",
                "production": "cd frontend && pnpm install && pnpm run build",
                "vite_url": "http://127.0.0.1:5173",
            },
        )

    @application.get(
        "/{frontend_path:path}",
        summary="Servir un chemin du frontend",
        response_description="Asset React ou index de fallback SPA",
    )
    async def frontend_files(frontend_path: str):
        """Sert un asset React sûr ou l'index pour le routage SPA côté client."""
        if not FRONTEND_DIST.is_dir():
            return JSONResponse(
                status_code=404,
                content={"detail": "Build React absent. Exécutez pnpm run build."},
            )
        requested_file = (FRONTEND_DIST / frontend_path).resolve()
        dist_root = FRONTEND_DIST.resolve()
        if requested_file == dist_root or dist_root not in requested_file.parents:
            requested_file = dist_root / "index.html"
        if requested_file.is_file():
            return FileResponse(requested_file)
        index_file = dist_root / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(status_code=404, content={"detail": "Frontend introuvable"})

    return application


app = create_app()
