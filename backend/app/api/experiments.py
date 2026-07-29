"""API dédiée aux expériences, profils versionnés et comparaisons shadow."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.models.backtest import BacktestStatus
from app.models.experiment import (
    ExperimentConfig,
    ProfileStatus,
    PromotionDecision,
    ShadowComparison,
)
from app.services.experiment_manager import ExperimentManager

router = APIRouter(tags=["experiments"])


def _manager(request: Request) -> ExperimentManager:
    return request.app.state.experiment_manager


async def _manifest_or_404(request: Request, experiment_id: str):
    manifest = await _manager(request).get(experiment_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Expérience introuvable")
    return manifest


@router.post("/api/experiments/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_experiment(config: ExperimentConfig, request: Request) -> dict[str, Any]:
    try:
        manifest = await _manager(request).create(config)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return manifest.model_dump(mode="json")


@router.get("/api/experiments/jobs/{experiment_id}")
async def get_experiment(experiment_id: str, request: Request) -> dict[str, Any]:
    return (await _manifest_or_404(request, experiment_id)).model_dump(mode="json")


@router.delete("/api/experiments/jobs/{experiment_id}", response_model=None)
async def cancel_experiment(experiment_id: str, request: Request) -> Response | dict[str, Any]:
    manifest = await _manifest_or_404(request, experiment_id)
    result = await _manager(request).cancel_or_delete(experiment_id)
    if manifest.status in {BacktestStatus.PENDING, BacktestStatus.RUNNING} and result:
        return result.model_dump(mode="json")
    return Response(status_code=204)


@router.get("/api/experiments/jobs/{experiment_id}/candidates")
async def candidates(
    experiment_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=128),
    eligible: bool | None = None,
) -> dict[str, Any]:
    manifest = await _manifest_or_404(request, experiment_id)
    items = [item for item in manifest.results if eligible is None or item.eligible == eligible]
    return {
        "items": [item.model_dump(mode="json") for item in items[offset : offset + limit]],
        "total": len(items),
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/experiments/jobs/{experiment_id}/candidate/{candidate_id}")
async def candidate(experiment_id: str, candidate_id: str, request: Request) -> dict[str, Any]:
    manifest = await _manifest_or_404(request, experiment_id)
    item = next(
        (result for result in manifest.results if result.candidate_id == candidate_id), None
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Candidat introuvable")
    return item.model_dump(mode="json")


@router.get("/api/experiments/jobs/{experiment_id}/walk-forward")
async def experiment_walk_forward(experiment_id: str, request: Request) -> Any:
    manifest = await _manifest_or_404(request, experiment_id)
    return {item.candidate_id: item.walk_forward for item in manifest.results}


@router.get("/api/experiments/jobs/{experiment_id}/sensitivity")
async def experiment_sensitivity(experiment_id: str, request: Request) -> Any:
    manifest = await _manifest_or_404(request, experiment_id)
    return {item.candidate_id: item.sensitivity for item in manifest.results}


@router.get("/api/experiments/jobs/{experiment_id}/exports")
async def experiment_exports(experiment_id: str, request: Request) -> Any:
    await _manifest_or_404(request, experiment_id)
    return {
        "manifest": f"/api/experiments/jobs/{experiment_id}/export?dataset=manifest",
        "candidates": f"/api/experiments/jobs/{experiment_id}/export?dataset=candidates",
        "folds": f"/api/experiments/jobs/{experiment_id}/export?dataset=folds",
        "sensitivity": f"/api/experiments/jobs/{experiment_id}/export?dataset=sensitivity",
    }


@router.get("/api/experiments/jobs/{experiment_id}/export")
async def export_experiment(
    experiment_id: str,
    request: Request,
    dataset: Literal["manifest", "candidates", "folds", "sensitivity"] = "manifest",
) -> Response:
    manifest = await _manifest_or_404(request, experiment_id)
    if dataset == "manifest":
        return Response(
            manifest.model_dump_json(indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{experiment_id}-manifest.json"'
            },
        )
    rows: list[dict[str, Any]] = []
    for result in manifest.results:
        if dataset == "candidates":
            rows.append(result.model_dump(mode="json", exclude={"walk_forward", "sensitivity"}))
        elif dataset == "folds":
            rows.extend(
                {"candidate_id": result.candidate_id, **fold} for fold in result.walk_forward
            )
        else:
            rows.append({"candidate_id": result.candidate_id, **result.sensitivity})
    return Response(
        _csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{experiment_id}-{dataset}.csv"'},
    )


@router.get("/api/signal-profiles")
async def profiles(request: Request) -> list[dict[str, Any]]:
    items = await _manager(request).repository.profiles()
    return [item.model_dump(mode="json") for item in items]


@router.get("/api/signal-profiles/{profile_id}")
async def profile(profile_id: str, request: Request) -> dict[str, Any]:
    item = await _manager(request).repository.get_profile(profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return item.model_dump(mode="json")


@router.get("/api/signal-profiles/{profile_id}/lifecycle")
async def profile_lifecycle(profile_id: str, request: Request) -> list[dict[str, Any]]:
    repository = _manager(request).repository
    if await repository.get_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return await repository.lifecycle(profile_id)


class PromotionRequest(BaseModel):
    experiment_id: str
    comment: str = Field(min_length=3, max_length=2_000)
    confirm: Literal[True]


@router.post("/api/signal-profiles/{profile_id}/promote")
async def promote(profile_id: str, payload: PromotionRequest, request: Request) -> dict[str, Any]:
    repository = _manager(request).repository
    profile_item = await repository.get_profile(profile_id)
    manifest = await _manifest_or_404(request, payload.experiment_id)
    if profile_item is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    result = next((item for item in manifest.results if item.candidate_id == profile_id), None)
    validation_median = result.metrics.get("validation", {}).get("net_median") if result else None
    oos_median = result.oos_metrics.get("net_median") if result else None
    test_median = result.final_test_metrics.get("net_median") if result else None
    max_oos_degradation = manifest.config.promotion_criteria.get("max_oos_degradation", 0.01)
    criteria = {
        "experiment_completed": manifest.status == BacktestStatus.COMPLETED,
        "candidate_eligible": bool(result and result.eligible),
        "candidate_selected": bool(result and result.selected),
        "confirmed_only": profile_item.snapshot_status == "confirmed",
        "profile_linked_to_experiment": profile_item.experiment_id == payload.experiment_id,
        "validation_net_nonnegative": isinstance(validation_median, (int, float))
        and validation_median >= 0,
        "oos_net_nonnegative": isinstance(oos_median, (int, float)) and oos_median >= 0,
        "final_test_net_nonnegative": isinstance(test_median, (int, float)) and test_median >= 0,
        "oos_degradation_bounded": isinstance(validation_median, (int, float))
        and isinstance(oos_median, (int, float))
        and validation_median - oos_median <= max_oos_degradation,
        "multiplicity_controlled": bool(
            result
            and result.adjusted_p_value is not None
            and result.adjusted_p_value <= manifest.config.multiplicity_alpha
        ),
    }
    approved = all(criteria.values())
    current = next(
        (item for item in await repository.profiles() if item.status == ProfileStatus.PRODUCTION),
        None,
    )
    decision = PromotionDecision(
        profile_id=profile_id,
        experiment_id=payload.experiment_id,
        approved=approved,
        criteria=criteria,
        comment=payload.comment,
        previous_profile_id=current.id if current else None,
    )
    await repository.save_decision(decision)
    if not approved:
        raise HTTPException(status_code=409, detail=decision.model_dump(mode="json"))
    return decision.model_dump(mode="json")


class RetireRequest(BaseModel):
    comment: str = Field(min_length=3, max_length=2_000)
    confirm: Literal[True]


class ShadowRequest(BaseModel):
    comment: str = Field(min_length=3, max_length=2_000)
    confirm: Literal[True]


@router.post("/api/signal-profiles/{profile_id}/shadow")
async def enable_shadow(
    profile_id: str, payload: ShadowRequest, request: Request
) -> dict[str, Any]:
    repository = _manager(request).repository
    profile_item = await repository.get_profile(profile_id)
    if profile_item is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    if profile_item.status not in {ProfileStatus.CANDIDATE, ProfileStatus.SHADOW}:
        raise HTTPException(status_code=409, detail="seul un profil candidat peut passer shadow")
    await repository.set_profile_status(
        profile_id,
        ProfileStatus.SHADOW.value,
        decision="shadow",
        comment=payload.comment,
        origin="human",
    )
    return {"profile_id": profile_id, "status": ProfileStatus.SHADOW.value}


@router.post("/api/signal-profiles/{profile_id}/retire")
async def retire(profile_id: str, payload: RetireRequest, request: Request) -> dict[str, Any]:
    repository = _manager(request).repository
    profile_item = await repository.get_profile(profile_id)
    if profile_item is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    if profile_item.status == ProfileStatus.PRODUCTION:
        raise HTTPException(
            status_code=409,
            detail="promouvoir ou restaurer un autre profil avant de retirer la production",
        )
    await repository.set_profile_status(
        profile_id,
        ProfileStatus.RETIRED.value,
        decision="retire",
        comment=payload.comment,
        origin="human",
    )
    return {
        "profile_id": profile_id,
        "status": ProfileStatus.RETIRED.value,
        "comment": payload.comment,
    }


@router.post("/api/shadow/comparisons", status_code=201)
async def record_shadow(comparison: ShadowComparison, request: Request) -> dict[str, int]:
    if not request.app.state.settings.shadow_mode_enabled:
        raise HTTPException(status_code=409, detail="mode shadow désactivé par configuration")
    if comparison.production_profile_id == comparison.candidate_profile_id and (
        comparison.production != comparison.candidate or comparison.divergence_reasons
    ):
        raise HTTPException(status_code=422, detail="un profil identique ne peut diverger")
    identifier = await _manager(request).repository.add_shadow(comparison)
    return {"id": identifier}


@router.get("/api/shadow/comparisons")
async def shadow_comparisons(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1_000),
    symbol: str | None = None,
) -> dict[str, Any]:
    items, total = await _manager(request).repository.shadows(
        offset=offset, limit=limit, symbol=symbol
    )
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/shadow/summary")
async def shadow_summary(request: Request, symbol: str | None = None) -> dict[str, Any]:
    items, total = await _manager(request).repository.shadows(offset=0, limit=1_000, symbol=symbol)
    divergent = sum(bool(item.divergence_reasons) for item in items)
    reasons: dict[str, int] = {}
    for item in items:
        for reason in item.divergence_reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "total": total,
        "sampled": len(items),
        "divergent": divergent,
        "agreement_rate": (len(items) - divergent) / len(items) if items else None,
        "reasons": reasons,
        "future_outcomes_available": sum(item.future_outcome is not None for item in items),
    }


def _csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fields = sorted({key for row in rows for key in row})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            }
        )
    return stream.getvalue()
