"""Routes REST et WebSocket dédiées aux jobs de scan."""

from __future__ import annotations

from typing import Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from app.core.settings import ScanConfig
from app.exporters.csv_exporter import results_to_csv
from app.models.scanner import ScanStatus
from app.services.exchange import create_exchange, load_filtered_symbols
from app.services.scan_manager import scan_manager

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


@router.get(
    "/config",
    summary="Lire la configuration de scan par défaut",
    response_description="Valeurs par défaut validées de ScanConfig",
)
async def get_default_config() -> dict:
    """Retourne un ``ScanConfig`` complet sérialisé en JSON."""
    return ScanConfig().model_dump(mode="json")


@router.get(
    "/markets",
    summary="Lister les marchés disponibles",
    response_description="Symboles CCXT triés correspondant aux filtres",
)
async def get_markets(
    quote: str = Query(default="USDC", description="Devise de cotation recherchée."),
    market_type: Literal["spot", "swap", "future"] = Query(
        default="spot", description="Type exact de marché CCXT."
    ),
) -> list[str]:
    """Charge et filtre les marchés, puis ferme systématiquement l'exchange."""
    config = ScanConfig(quote=quote, market_type=market_type)
    exchange = create_exchange(config)
    try:
        return await load_filtered_symbols(exchange, config)
    finally:
        await exchange.close()


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Démarrer un scan de marché",
    response_description="Job créé et planifié",
)
async def start_scan(config: ScanConfig) -> dict:
    """Enregistre la configuration validée et planifie le scan en arrière-plan."""
    job = await scan_manager.create_job(config)
    return job.public_payload()


@router.get(
    "/jobs/{job_id}",
    summary="Consulter un job de scan",
    response_description="État courant du job sans ses résultats détaillés",
    responses={404: {"description": "Job de scan introuvable"}},
)
async def get_scan(job_id: str) -> dict:
    """Retourne le snapshot public courant d'un job présent en mémoire."""
    job = scan_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan introuvable")
    return job.public_payload()


@router.get(
    "/jobs/{job_id}/results",
    summary="Lire les résultats d'un scan terminé",
    response_description="Job accompagné de ses résultats détaillés",
    responses={
        404: {"description": "Job de scan introuvable"},
        409: {"description": "Scan encore en cours ou en échec"},
    },
)
async def get_results(job_id: str) -> dict:
    """Expose les résultats d'un job ``completed`` ou ``cancelled``."""
    job = scan_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan introuvable")
    if job.status not in {ScanStatus.COMPLETED, ScanStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Le scan n'est pas terminé")
    return job.public_payload(include_results=True)


@router.get(
    "/jobs/{job_id}/export.csv",
    summary="Exporter les résultats au format CSV",
    response_description="Fichier CSV téléchargeable",
    responses={
        404: {"description": "Job de scan introuvable"},
        409: {"description": "Scan encore en cours ou en échec"},
    },
)
async def export_results(job_id: str) -> Response:
    """Sérialise les résultats finaux ou partiels d'un job terminé."""
    job = scan_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan introuvable")
    if job.status not in {ScanStatus.COMPLETED, ScanStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Le scan n'est pas terminé")
    content = results_to_csv(job.results)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="scan-{job.id}.csv"'},
    )


@router.delete(
    "/jobs/{job_id}",
    summary="Annuler un scan",
    response_description="État du job après la demande d'annulation",
    responses={404: {"description": "Job de scan introuvable"}},
)
async def cancel_scan(job_id: str) -> dict:
    """Annule la tâche active; un job déjà final reste inchangé."""
    job = await scan_manager.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan introuvable")
    return job.public_payload()


@router.websocket("/ws/{job_id}")
async def scan_websocket(websocket: WebSocket, job_id: str) -> None:
    """Publie le snapshot initial puis chaque changement de progression.

    Un job absent provoque une fermeture 4404 avant acceptation. La connexion
    d'un job existant se termine après l'émission de son premier état final.
    """
    job = scan_manager.get_job(job_id)
    if job is None:
        await websocket.close(code=4404, reason="Scan introuvable")
        return

    await websocket.accept()
    version = -1
    try:
        while True:
            current = scan_manager.get_job(job_id)
            if current is None:
                await websocket.close(code=4404, reason="Scan introuvable")
                return
            if version < 0:
                payload = current.public_payload()
                version = scan_manager.current_version(job_id)
            else:
                changed = await scan_manager.wait_for_change(job_id, version)
                if changed is None:
                    return
                version, payload = changed
            await websocket.send_json(payload)
            if current.status in {
                ScanStatus.COMPLETED,
                ScanStatus.FAILED,
                ScanStatus.CANCELLED,
            }:
                return
    except WebSocketDisconnect:
        return
