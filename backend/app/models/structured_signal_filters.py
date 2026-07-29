"""Contrats Pydantic du filtre versionné appliqué aux signaux structurés."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain.indicators.types import Availability, SignalDirection

StructuredFilterIndicator: TypeAlias = Literal["macd", "bollinger", "stochastic"]
StructuredFilterMatch: TypeAlias = Literal["all", "any"]
NonEmptyFilterValue: TypeAlias = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class _StrictFilterModel(BaseModel):
    """Base commune interdisant toute extension implicite du contrat v1."""

    model_config = ConfigDict(extra="forbid")


class DirectionFilterCondition(_StrictFilterModel):
    """Condition portant sur le biais directionnel contractuel."""

    field: Literal["direction"]
    values: list[SignalDirection] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def reject_duplicates(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("values ne doit pas contenir de doublons")
        return values


class StatusFilterCondition(_StrictFilterModel):
    """Condition portant sur la disponibilité du calcul."""

    field: Literal["status"]
    values: list[Availability] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def reject_duplicates(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("values ne doit pas contenir de doublons")
        return values


class SignalFilterCondition(_StrictFilterModel):
    """Condition portant sur un événement ou une classe native."""

    field: Literal["signal"]
    values: list[NonEmptyFilterValue] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def reject_duplicates(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("values ne doit pas contenir de doublons")
        return values


class StateFilterCondition(_StrictFilterModel):
    """Condition portant sur l'état persistant d'un indicateur."""

    field: Literal["state"]
    values: list[NonEmptyFilterValue] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def reject_duplicates(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("values ne doit pas contenir de doublons")
        return values


StructuredFilterCondition = Annotated[
    DirectionFilterCondition | SignalFilterCondition | StateFilterCondition | StatusFilterCondition,
    Field(discriminator="field"),
]


class StructuredIndicatorFilter(_StrictFilterModel):
    """Groupe de conditions d'un indicateur.

    Une liste ``conditions`` vide est une neutralisation explicite du filtre
    pour cet indicateur. Sa présence empêche donc le fallback legacy.
    """

    match: StructuredFilterMatch = "all"
    conditions: list[StructuredFilterCondition] = Field(default_factory=list)


class StructuredSignalFilters(_StrictFilterModel):
    """Version 1 du contrat additif de filtres de signaux."""

    version: Literal[1]
    indicators: dict[StructuredFilterIndicator, StructuredIndicatorFilter] = Field(
        default_factory=dict
    )


__all__ = [
    "DirectionFilterCondition",
    "SignalFilterCondition",
    "StateFilterCondition",
    "StatusFilterCondition",
    "StructuredFilterCondition",
    "StructuredFilterIndicator",
    "StructuredFilterMatch",
    "StructuredIndicatorFilter",
    "StructuredSignalFilters",
]
