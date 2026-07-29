"""Types internes décrivant l'issue de l'analyse d'un symbole."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterator

from app.models.scanner import ScanResult


class AnalysisStatus(StrEnum):
    """Issue interne, distincte du statut global d'un job de scan."""

    SUCCESS = "success"
    FILTERED = "filtered"
    ERROR = "error"


@dataclass(slots=True)
class AnalysisOutcome:
    """Résultat interne d'une analyse isolée.

    Un succès porte un ``ScanResult``; un rejet par filtre n'en porte pas;
    une erreur peut fournir un message destiné aux journaux et compteurs.
    """

    status: AnalysisStatus
    result: ScanResult | None = None
    error: str | None = None

    def __iter__(self) -> Iterator[object]:
        """Preserve legacy ``status, result = outcome`` unpacking."""
        yield self.status.value
        yield self.result
