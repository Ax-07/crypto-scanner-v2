"""Validation, sémantique et parité des filtres structurés v1."""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from app.core.settings import ScanConfig
from app.domain.indicators import check_signal_filters
from app.domain.signal_filters import (
    LEGACY_FILTER_MATRIX,
    check_structured_signal_filters,
    include_disabled_filter_signals,
    legacy_filters_to_structured,
    resolve_effective_signal_filters,
)
from app.models.structured_signal_filters import StructuredSignalFilters


def signal(
    *,
    direction: str = "neutral",
    event: str | None = "neutral",
    state: str | None = "neutral",
    status: str = "available",
) -> dict[str, object]:
    return {
        "status": status,
        "direction": direction,
        "signal": event,
        "state": state,
        "strength": 0.0,
        "reason": None,
        "raw_value": None,
    }


def contract(
    indicator: str,
    *,
    match: str = "all",
    conditions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "version": 1,
        "indicators": {
            indicator: {
                "match": match,
                "conditions": conditions or [],
            }
        },
    }


def test_version_one_and_partial_contract_are_valid() -> None:
    parsed = StructuredSignalFilters.model_validate(
        contract(
            "macd",
            conditions=[{"field": "direction", "values": ["bullish", "neutral"]}],
        )
    )
    assert parsed.version == 1
    assert set(parsed.indicators) == {"macd"}


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 2, "indicators": {}},
        {"version": 1, "indicators": {"rsi": {"match": "all", "conditions": []}}},
        contract("macd", conditions=[{"field": "strength", "values": ["1"]}]),
        contract("macd", conditions=[{"field": "direction", "values": []}]),
        contract("macd", conditions=[{"field": "direction", "values": ["bullish", "bullish"]}]),
        contract("macd", conditions=[{"field": "direction", "values": ["up"]}]),
        contract("macd", conditions=[{"field": "status", "values": ["unavailable"]}]),
        contract("macd", conditions=[{"field": "signal", "values": [""]}]),
        {
            "version": 1,
            "indicators": {"macd": {"match": "all", "conditions": [], "unknown": True}},
        },
    ],
)
def test_invalid_contracts_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StructuredSignalFilters.model_validate(payload)


def test_values_are_or_conditions_follow_match_and_indicators_are_all() -> None:
    signals = {
        "macd": signal(direction="bullish", event="above_signal"),
        "bollinger": signal(direction="bullish", event="lower_band_reentry", state="neutral"),
    }
    assert check_structured_signal_filters(
        indicator_signals=signals,
        filters={
            "version": 1,
            "indicators": {
                "macd": {
                    "match": "all",
                    "conditions": [{"field": "direction", "values": ["bullish", "neutral"]}],
                },
                "bollinger": {
                    "match": "any",
                    "conditions": [
                        {"field": "state", "values": ["oversold"]},
                        {"field": "signal", "values": ["lower_band_reentry"]},
                    ],
                },
            },
        },
    )
    assert not check_structured_signal_filters(
        indicator_signals=signals,
        filters={
            "version": 1,
            "indicators": {
                "macd": {
                    "match": "all",
                    "conditions": [{"field": "direction", "values": ["bullish"]}],
                },
                "bollinger": {
                    "match": "all",
                    "conditions": [
                        {"field": "state", "values": ["oversold"]},
                        {"field": "signal", "values": ["lower_band_reentry"]},
                    ],
                },
            },
        },
    )


def test_status_is_available_implicitly_and_explicit_status_is_strict() -> None:
    unavailable = {"macd": signal(status="insufficient_data", direction="neutral", event=None)}
    direction_filter = contract("macd", conditions=[{"field": "direction", "values": ["neutral"]}])
    status_filter = contract(
        "macd", conditions=[{"field": "status", "values": ["insufficient_data"]}]
    )
    assert not check_structured_signal_filters(
        indicator_signals=unavailable, filters=direction_filter
    )
    assert check_structured_signal_filters(indicator_signals=unavailable, filters=status_filter)
    assert not check_structured_signal_filters(indicator_signals={}, filters=status_filter)


def test_disabled_status_uses_a_local_signal_without_mutating_public_results() -> None:
    public_signals: dict = {}
    filter_signals = include_disabled_filter_signals(
        indicator_signals=public_signals,
        disabled_indicators=["macd"],
    )
    assert public_signals == {}
    assert check_structured_signal_filters(
        indicator_signals=filter_signals,
        filters=contract(
            "macd",
            conditions=[{"field": "status", "values": ["disabled"]}],
        ),
    )


def test_empty_structured_group_disables_legacy_fallback_for_that_indicator() -> None:
    effective = resolve_effective_signal_filters(
        structured_filters=contract("macd"),
        filter_macd=["bearish"],
        filter_bb=["oversold"],
        filter_stoch=None,
    )
    assert effective is not None
    indicators = effective["indicators"]
    assert isinstance(indicators, dict)
    assert indicators["macd"]["conditions"] == []
    assert "bollinger" in indicators
    assert check_structured_signal_filters(
        indicator_signals={
            "macd": signal(direction="bullish"),
            "bollinger": signal(state="oversold"),
        },
        filters=effective,
    )


def test_structured_filter_has_priority_and_legacy_fallback_is_per_indicator() -> None:
    effective = resolve_effective_signal_filters(
        structured_filters=contract(
            "macd", conditions=[{"field": "direction", "values": ["bullish"]}]
        ),
        filter_macd=["bearish"],
        filter_bb=["oversold"],
        filter_stoch=None,
    )
    assert effective is not None
    assert check_structured_signal_filters(
        indicator_signals={
            "macd": signal(direction="bullish"),
            "bollinger": signal(state="oversold"),
        },
        filters=effective,
    )
    assert not check_structured_signal_filters(
        indicator_signals={
            "macd": signal(direction="bullish"),
            "bollinger": signal(state="neutral"),
        },
        filters=effective,
    )


LEGACY_VALUES = {
    "macd": ["bullish", "bearish", "neutral"],
    "bollinger": [
        "oversold",
        "near_oversold",
        "neutral",
        "near_overbought",
        "overbought",
    ],
    "stochastic": ["bullish_cross", "oversold", "neutral", "bearish_cross", "overbought"],
}


@pytest.mark.parametrize("indicator", LEGACY_VALUES)
def test_legacy_matrix_is_complete(indicator: str) -> None:
    assert set(LEGACY_FILTER_MATRIX[indicator]) == set(LEGACY_VALUES[indicator])


@pytest.mark.parametrize(
    ("indicator", "allowed"),
    [
        (indicator, list(values))
        for indicator, universe in LEGACY_VALUES.items()
        for size in range(1, len(universe) + 1)
        for values in itertools.combinations(universe, size)
    ],
)
def test_every_legacy_combination_has_exact_structured_parity(
    indicator: str, allowed: list[str]
) -> None:
    converted = legacy_filters_to_structured(
        filter_macd=allowed if indicator == "macd" else None,
        filter_bb=allowed if indicator == "bollinger" else None,
        filter_stoch=allowed if indicator == "stochastic" else None,
    )
    assert converted is not None
    for current in LEGACY_VALUES[indicator]:
        legacy = check_signal_filters(
            macd_signal=current if indicator == "macd" else None,
            bb_position=current if indicator == "bollinger" else None,
            stoch_signal=current if indicator == "stochastic" else None,
            filter_macd=allowed if indicator == "macd" else None,
            filter_bb=allowed if indicator == "bollinger" else None,
            filter_stoch=allowed if indicator == "stochastic" else None,
        )
        structured_signal = (
            signal(direction=current)
            if indicator == "macd"
            else (
                signal(state=current)
                if indicator == "bollinger"
                else signal(
                    event=current, state=("oversold" if current == "bullish_cross" else current)
                )
            )
        )
        assert (
            check_structured_signal_filters(
                indicator_signals={indicator: structured_signal},
                filters=converted,
            )
            is legacy
        )


def test_stochastic_cross_or_state_is_representable_without_forcing_and() -> None:
    filters = contract(
        "stochastic",
        match="any",
        conditions=[
            {"field": "signal", "values": ["bullish_cross"]},
            {"field": "state", "values": ["oversold"]},
        ],
    )
    assert check_structured_signal_filters(
        indicator_signals={"stochastic": signal(event="bullish_cross", state="neutral")},
        filters=filters,
    )
    assert check_structured_signal_filters(
        indicator_signals={"stochastic": signal(event="oversold", state="oversold")},
        filters=filters,
    )
    assert not check_structured_signal_filters(
        indicator_signals={"stochastic": signal(event="neutral", state="neutral")},
        filters=filters,
    )


def test_scan_config_accepts_legacy_new_and_coexistence() -> None:
    assert ScanConfig(filter_macd_signal=["bullish"]).structured_signal_filters is None
    structured = StructuredSignalFilters.model_validate(
        contract("macd", conditions=[{"field": "direction", "values": ["bullish"]}])
    )
    config = ScanConfig(
        filter_macd_signal=["bearish"],
        structured_signal_filters=structured,
    )
    assert config.filter_macd_signal == ["bearish"]
    assert config.structured_signal_filters == structured
