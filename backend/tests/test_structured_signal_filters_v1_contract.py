"""Garde-fous JSON et oracle de compatibilité des filtres structurés v1."""

from __future__ import annotations

import itertools
import json
import hashlib
from collections.abc import Mapping, Sequence
from typing import cast

import pytest
from pydantic import ValidationError

from app.core.settings import OPTIONAL_INDICATOR_EXTENSION_FIELDS, ScanConfig
from app.domain.indicators import check_signal_filters
from app.domain.indicators.types import IndicatorSignal
from app.domain.signal_filters import (
    check_structured_signal_filters,
    include_disabled_filter_signals,
    legacy_filters_to_structured,
    resolve_effective_signal_filters,
)
from app.models.structured_signal_filters import StructuredSignalFilters

LEGACY_VALUES = {
    "macd": ("bullish", "bearish", "neutral"),
    "bollinger": (
        "oversold",
        "near_oversold",
        "neutral",
        "near_overbought",
        "overbought",
    ),
    "stochastic": (
        "bullish_cross",
        "oversold",
        "neutral",
        "bearish_cross",
        "overbought",
    ),
}


def explicit_json(source: str) -> dict[str, object]:
    """Charge un payload littéral afin de tester la vraie frontière JSON."""
    return cast(dict[str, object], json.loads(source))


def profile_fingerprint(config: ScanConfig) -> str:
    """Reproduit le fingerprint canonique du profil d'évaluation."""
    excluded = {
        name for name in OPTIONAL_INDICATOR_EXTENSION_FIELDS if getattr(config, name, None) is None
    }

    if config.structured_signal_filters is None:
        excluded.add("structured_signal_filters")

    payload = config.model_dump(
        mode="json",
        exclude=excluded,
    )

    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )


def indicator_signal(
    *,
    direction: str = "neutral",
    signal: str | None = "neutral",
    state: str | None = "neutral",
    status: str = "available",
) -> IndicatorSignal:
    """Construit un signal minimal lisible pour les tests de contrat."""
    return cast(
        IndicatorSignal,
        {
            "status": status,
            "direction": direction,
            "signal": signal,
            "state": state,
            "strength": 0.0,
            "reason": None,
            "raw_value": None,
        },
    )


def assert_legacy_structured_equivalent(
    *,
    indicator: str,
    legacy_filters: Sequence[str] | None,
    current_value: str | None,
    structured_signal: IndicatorSignal | None,
) -> None:
    """Compare les deux moteurs et produit un diagnostic de parité complet."""
    legacy_arguments = {
        "macd_signal": current_value if indicator == "macd" else None,
        "bb_position": current_value if indicator == "bollinger" else None,
        "stoch_signal": current_value if indicator == "stochastic" else None,
        "filter_macd": legacy_filters if indicator == "macd" else None,
        "filter_bb": legacy_filters if indicator == "bollinger" else None,
        "filter_stoch": legacy_filters if indicator == "stochastic" else None,
    }
    legacy_result = check_signal_filters(**legacy_arguments)
    converted = legacy_filters_to_structured(
        filter_macd=legacy_arguments["filter_macd"],
        filter_bb=legacy_arguments["filter_bb"],
        filter_stoch=legacy_arguments["filter_stoch"],
    )
    structured_result = (
        True
        if converted is None
        else check_structured_signal_filters(
            indicator_signals=(
                {indicator: structured_signal} if structured_signal is not None else {}
            ),
            filters=converted,
        )
    )
    assert structured_result is legacy_result, (
        f"divergence {indicator}: filtres={legacy_filters!r}, "
        f"valeur={current_value!r}, legacy={legacy_result}, "
        f"structured={structured_result}, contrat={converted!r}, "
        f"signal={structured_signal!r}"
    )


@pytest.mark.parametrize(
    "payload",
    [
        explicit_json("""{"version": 1, "indicators": {}}"""),
        explicit_json("""
            {
              "version": 1,
              "indicators": {
                "macd": {
                  "match": "all",
                  "conditions": [
                    {"field": "direction", "values": ["bullish"]}
                  ]
                }
              }
            }
            """),
        explicit_json("""
            {
              "version": 1,
              "indicators": {
                "bollinger": {
                  "match": "any",
                  "conditions": [
                    {"field": "state", "values": ["oversold"]},
                    {"field": "signal", "values": ["lower_band_reentry"]}
                  ]
                }
              }
            }
            """),
        explicit_json("""
            {
              "version": 1,
              "indicators": {
                "stochastic": {
                  "match": "any",
                  "conditions": [
                    {
                      "field": "signal",
                      "values": ["bullish_cross", "oversold"]
                    }
                  ]
                }
              }
            }
            """),
        explicit_json("""
            {
              "version": 1,
              "indicators": {
                "macd": {
                  "match": "all",
                  "conditions": [
                    {"field": "status", "values": ["available"]},
                    {"field": "direction", "values": ["bullish"]}
                  ]
                }
              }
            }
            """),
    ],
)
def test_official_json_payloads_are_frozen(payload: dict[str, object]) -> None:
    parsed = StructuredSignalFilters.model_validate(payload)
    assert parsed.model_dump(mode="json") == payload


@pytest.mark.parametrize(
    "payload",
    [
        '{"version": 2, "indicators": {}}',
        '{"version": 1, "indicators": {"rsi": {"match": "all", "conditions": []}}}',
        '{"version": 1, "indicators": {"macd": {"match": "none", "conditions": []}}}',
        (
            '{"version": 1, "indicators": {"macd": {"match": "all", '
            '"conditions": [{"field": "strength", "values": ["1"]}]}}}'
        ),
        (
            '{"version": 1, "indicators": {"macd": {"match": "all", '
            '"conditions": [{"field": "direction", "values": []}]}}}'
        ),
        (
            '{"version": 1, "indicators": {"macd": {"match": "all", '
            '"conditions": [{"field": "direction", '
            '"values": ["bullish", "bullish"]}]}}}'
        ),
        (
            '{"version": 1, "indicators": {"macd": {"match": "all", '
            '"conditions": [{"field": "direction", "values": ["up"]}]}}}'
        ),
        (
            '{"version": 1, "indicators": {"macd": {"match": "all", '
            '"conditions": [{"field": "status", "values": ["unavailable"]}]}}}'
        ),
        (
            '{"version": 1, "indicators": {"macd": {"match": "all", '
            '"conditions": [{"field": "signal", "values": ["  "]}]}}}'
        ),
        (
            '{"version": 1, "indicators": {"macd": {"match": "all", '
            '"conditions": [], "unknown": true}}}'
        ),
    ],
)
def test_expected_json_rejections_are_frozen(payload: str) -> None:
    with pytest.raises(ValidationError):
        StructuredSignalFilters.model_validate_json(payload)


def _legacy_filter_sets(indicator: str) -> list[Sequence[str] | None]:
    values = LEGACY_VALUES[indicator]
    return [
        None,
        [],
        *[
            list(combination)
            for size in range(1, len(values) + 1)
            for combination in itertools.combinations(values, size)
        ],
    ]


@pytest.mark.parametrize("indicator", LEGACY_VALUES)
def test_complete_legacy_parity_matrix(indicator: str) -> None:
    for filters in _legacy_filter_sets(indicator):
        for current in LEGACY_VALUES[indicator]:
            structured = (
                indicator_signal(direction=current)
                if indicator == "macd"
                else (
                    indicator_signal(state=current)
                    if indicator == "bollinger"
                    else indicator_signal(
                        signal=current,
                        state=(
                            "oversold"
                            if current == "bullish_cross"
                            else ("overbought" if current == "bearish_cross" else current)
                        ),
                    )
                )
            )
            assert_legacy_structured_equivalent(
                indicator=indicator,
                legacy_filters=filters,
                current_value=current,
                structured_signal=structured,
            )


@pytest.mark.parametrize("indicator", LEGACY_VALUES)
@pytest.mark.parametrize("filters", [None, []])
def test_none_and_empty_legacy_filters_accept_absent_signals(
    indicator: str, filters: Sequence[str] | None
) -> None:
    assert_legacy_structured_equivalent(
        indicator=indicator,
        legacy_filters=filters,
        current_value=None,
        structured_signal=None,
    )


@pytest.mark.parametrize(
    ("indicator", "signal", "expected"),
    [
        ("macd", indicator_signal(direction="bullish"), "bullish"),
        ("macd", indicator_signal(direction="bearish"), "bearish"),
        ("macd", indicator_signal(direction="neutral"), "neutral"),
        (
            "macd",
            indicator_signal(direction="bullish", signal="bullish_cross"),
            "bullish",
        ),
        (
            "macd",
            indicator_signal(direction="bearish", signal="bearish_cross"),
            "bearish",
        ),
        (
            "macd",
            indicator_signal(direction="bullish", signal="above_signal"),
            "bullish",
        ),
        (
            "macd",
            indicator_signal(direction="bearish", signal="below_signal"),
            "bearish",
        ),
        *[
            ("bollinger", indicator_signal(state=value), value)
            for value in LEGACY_VALUES["bollinger"]
        ],
        (
            "bollinger",
            indicator_signal(signal="lower_band_breakout", state="oversold"),
            "oversold",
        ),
        (
            "bollinger",
            indicator_signal(signal="lower_band_reentry", state="near_oversold"),
            "near_oversold",
        ),
        (
            "bollinger",
            indicator_signal(signal="upper_band_breakout", state="overbought"),
            "overbought",
        ),
        (
            "bollinger",
            indicator_signal(signal="upper_band_reentry", state="near_overbought"),
            "near_overbought",
        ),
        *[
            (
                "stochastic",
                indicator_signal(
                    signal=value,
                    state=value if value in {"oversold", "neutral", "overbought"} else "neutral",
                ),
                value,
            )
            for value in LEGACY_VALUES["stochastic"]
        ],
    ],
)
def test_all_historical_classifications_use_the_frozen_dimension(
    indicator: str, signal: IndicatorSignal, expected: str
) -> None:
    converted = legacy_filters_to_structured(
        filter_macd=[expected] if indicator == "macd" else None,
        filter_bb=[expected] if indicator == "bollinger" else None,
        filter_stoch=[expected] if indicator == "stochastic" else None,
    )
    assert converted is not None
    assert check_structured_signal_filters(
        indicator_signals={indicator: signal},
        filters=converted,
    )


def test_stochastic_legacy_reads_signal_and_never_state() -> None:
    converted = legacy_filters_to_structured(
        filter_macd=None,
        filter_bb=None,
        filter_stoch=["oversold"],
    )
    assert converted is not None
    crossing_in_oversold = indicator_signal(
        direction="bullish",
        signal="bullish_cross",
        state="oversold",
    )
    assert not check_structured_signal_filters(
        indicator_signals={"stochastic": crossing_in_oversold},
        filters=converted,
    )


@pytest.mark.parametrize("match", ["all", "any"])
@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        ([], True),
        ([{"field": "direction", "values": ["bullish"]}], True),
        ([{"field": "direction", "values": ["bearish"]}], False),
    ],
)
def test_zero_or_one_condition_rules(
    match: str, conditions: list[dict[str, object]], expected: bool
) -> None:
    filters = {
        "version": 1,
        "indicators": {"macd": {"match": match, "conditions": conditions}},
    }
    assert (
        check_structured_signal_filters(
            indicator_signals={
                "macd": indicator_signal(
                    direction="bullish",
                    signal="bullish_cross",
                )
            },
            filters=filters,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("match", "conditions", "expected"),
    [
        (
            "all",
            [
                {"field": "direction", "values": ["bullish", "neutral"]},
                {"field": "signal", "values": ["bullish_cross"]},
            ],
            True,
        ),
        (
            "all",
            [
                {"field": "direction", "values": ["bullish"]},
                {"field": "signal", "values": ["bearish_cross"]},
            ],
            False,
        ),
        (
            "any",
            [
                {"field": "direction", "values": ["bearish"]},
                {"field": "signal", "values": ["bullish_cross"]},
            ],
            True,
        ),
        (
            "any",
            [
                {"field": "direction", "values": ["bearish"]},
                {"field": "signal", "values": ["bearish_cross"]},
            ],
            False,
        ),
    ],
)
def test_multiple_condition_all_and_any_rules(
    match: str,
    conditions: list[dict[str, object]],
    expected: bool,
) -> None:
    filters = {
        "version": 1,
        "indicators": {"macd": {"match": match, "conditions": conditions}},
    }
    assert (
        check_structured_signal_filters(
            indicator_signals={
                "macd": indicator_signal(
                    direction="bullish",
                    signal="bullish_cross",
                )
            },
            filters=filters,
        )
        is expected
    )


@pytest.mark.parametrize(
    "status",
    ["available", "insufficient_data", "invalid_data", "disabled"],
)
def test_explicit_status_conditions(status: str) -> None:
    filters = {
        "version": 1,
        "indicators": {
            "macd": {
                "match": "all",
                "conditions": [{"field": "status", "values": [status]}],
            }
        },
    }
    assert check_structured_signal_filters(
        indicator_signals={"macd": indicator_signal(status=status, signal=None, state=None)},
        filters=filters,
    )


@pytest.mark.parametrize("status", ["insufficient_data", "invalid_data", "disabled"])
def test_business_condition_implicitly_requires_available(status: str) -> None:
    filters = {
        "version": 1,
        "indicators": {
            "macd": {
                "match": "all",
                "conditions": [{"field": "direction", "values": ["neutral"]}],
            }
        },
    }
    assert not check_structured_signal_filters(
        indicator_signals={
            "macd": indicator_signal(
                status=status,
                direction="neutral",
                signal=None,
                state=None,
            )
        },
        filters=filters,
    )


def test_absent_indicator_never_matches_a_non_empty_group() -> None:
    filters = {
        "version": 1,
        "indicators": {
            "macd": {
                "match": "any",
                "conditions": [{"field": "status", "values": ["insufficient_data", "disabled"]}],
            }
        },
    }
    assert not check_structured_signal_filters(
        indicator_signals={},
        filters=filters,
    )


def test_disabled_view_is_local_and_not_part_of_the_public_mapping() -> None:
    public: dict[str, IndicatorSignal] = {}
    local = include_disabled_filter_signals(
        indicator_signals=public,
        disabled_indicators=["macd"],
    )
    assert public == {}
    assert local["macd"]["status"] == "disabled"


@pytest.mark.parametrize(
    ("structured_indicator", "legacy_indicator", "legacy_value", "signal"),
    [
        (
            "macd",
            "bollinger",
            "oversold",
            {
                "macd": indicator_signal(direction="bullish"),
                "bollinger": indicator_signal(state="oversold"),
            },
        ),
        (
            "bollinger",
            "macd",
            "bullish",
            {
                "bollinger": indicator_signal(state="neutral"),
                "macd": indicator_signal(direction="bullish"),
            },
        ),
        (
            "stochastic",
            "macd",
            "bullish",
            {
                "stochastic": indicator_signal(signal="bearish_cross"),
                "macd": indicator_signal(direction="bullish"),
            },
        ),
    ],
)
def test_mixed_contract_fallback_is_per_indicator(
    structured_indicator: str,
    legacy_indicator: str,
    legacy_value: str,
    signal: Mapping[str, IndicatorSignal],
) -> None:
    structured = {
        "version": 1,
        "indicators": {
            structured_indicator: {
                "match": "all",
                "conditions": [],
            }
        },
    }
    legacy = {
        "filter_macd": [legacy_value] if legacy_indicator == "macd" else None,
        "filter_bb": [legacy_value] if legacy_indicator == "bollinger" else None,
        "filter_stoch": ([legacy_value] if legacy_indicator == "stochastic" else None),
    }
    effective = resolve_effective_signal_filters(
        structured_filters=structured,
        **legacy,
    )
    assert effective is not None
    assert check_structured_signal_filters(
        indicator_signals=signal,
        filters=effective,
    )


@pytest.mark.parametrize(
    ("indicator", "legacy_value", "structured_field", "structured_value", "signal"),
    [
        (
            "macd",
            "bearish",
            "direction",
            "bullish",
            indicator_signal(direction="bullish"),
        ),
        (
            "bollinger",
            "oversold",
            "state",
            "overbought",
            indicator_signal(state="overbought"),
        ),
        (
            "stochastic",
            "bearish_cross",
            "signal",
            "bullish_cross",
            indicator_signal(signal="bullish_cross"),
        ),
    ],
)
def test_structured_group_has_priority_for_each_indicator(
    indicator: str,
    legacy_value: str,
    structured_field: str,
    structured_value: str,
    signal: IndicatorSignal,
) -> None:
    effective = resolve_effective_signal_filters(
        structured_filters={
            "version": 1,
            "indicators": {
                indicator: {
                    "match": "all",
                    "conditions": [
                        {
                            "field": structured_field,
                            "values": [structured_value],
                        }
                    ],
                }
            },
        },
        filter_macd=[legacy_value] if indicator == "macd" else None,
        filter_bb=[legacy_value] if indicator == "bollinger" else None,
        filter_stoch=[legacy_value] if indicator == "stochastic" else None,
    )
    assert effective is not None
    assert check_structured_signal_filters(
        indicator_signals={indicator: signal},
        filters=effective,
    )


@pytest.mark.parametrize(
    ("indicator", "legacy_value"),
    [
        ("macd", "bearish"),
        ("bollinger", "oversold"),
        ("stochastic", "bearish_cross"),
    ],
)
def test_empty_group_neutralizes_legacy_for_each_indicator(
    indicator: str, legacy_value: str
) -> None:
    effective = resolve_effective_signal_filters(
        structured_filters={
            "version": 1,
            "indicators": {
                indicator: {
                    "match": "any",
                    "conditions": [],
                }
            },
        },
        filter_macd=[legacy_value] if indicator == "macd" else None,
        filter_bb=[legacy_value] if indicator == "bollinger" else None,
        filter_stoch=[legacy_value] if indicator == "stochastic" else None,
    )
    assert effective is not None
    assert check_structured_signal_filters(
        indicator_signals={},
        filters=effective,
    )


def fingerprint_config(**changes: object) -> ScanConfig:
    values: dict[str, object] = {
        "use_rsi": False,
        "use_ma": False,
        "use_macd": False,
        "use_bollinger": False,
        "use_stochastic": False,
        "use_confluence_score": False,
    }
    values.update(changes)
    return ScanConfig(**values)


def test_legacy_fingerprint_remains_frozen_when_new_field_is_absent() -> None:
    config = fingerprint_config(filter_macd_signal=["bullish"])
    assert config.structured_signal_filters is None
    assert (
        profile_fingerprint(config)
        == "sha256:17f402455510a523e8557cf7d9ba091aca0d8338a563ca0b51421d02d23bd237"
    )


def test_structured_and_mixed_fingerprints_are_deterministic_and_distinct() -> None:
    structured = fingerprint_config(
        filter_macd_signal=["bullish"],
        structured_signal_filters={
            "version": 1,
            "indicators": {
                "macd": {
                    "match": "all",
                    "conditions": [{"field": "direction", "values": ["bullish"]}],
                }
            },
        },
    )
    mixed = fingerprint_config(
        filter_macd_signal=["bearish"],
        structured_signal_filters={
            "version": 1,
            "indicators": {
                "macd": {
                    "match": "all",
                    "conditions": [],
                }
            },
        },
    )
    assert (
        profile_fingerprint(structured)
        == "sha256:804665319a48a8120d39d3ef6113e245f2f8384f4edc0c97a868fc6e9802ff6b"
    )
    assert (
        profile_fingerprint(mixed)
        == "sha256:47bad9c58f6ce1b54790c232005510cf1550bd62493d6d6e571d94781a28c42b"
    )
    assert profile_fingerprint(structured) != profile_fingerprint(mixed)


def test_fingerprint_sorts_object_keys_but_preserves_list_order() -> None:
    first = fingerprint_config(
        structured_signal_filters={
            "version": 1,
            "indicators": {
                "macd": {
                    "match": "any",
                    "conditions": [
                        {
                            "field": "direction",
                            "values": ["bullish", "neutral"],
                        }
                    ],
                },
                "bollinger": {"match": "all", "conditions": []},
            },
        }
    )
    reversed_keys = fingerprint_config(
        structured_signal_filters={
            "indicators": {
                "bollinger": {"conditions": [], "match": "all"},
                "macd": {
                    "conditions": [
                        {
                            "values": ["bullish", "neutral"],
                            "field": "direction",
                        }
                    ],
                    "match": "any",
                },
            },
            "version": 1,
        }
    )
    reversed_values = fingerprint_config(
        structured_signal_filters={
            "version": 1,
            "indicators": {
                "macd": {
                    "match": "any",
                    "conditions": [
                        {
                            "field": "direction",
                            "values": ["neutral", "bullish"],
                        }
                    ],
                },
                "bollinger": {"match": "all", "conditions": []},
            },
        }
    )
    assert profile_fingerprint(first) == profile_fingerprint(reversed_keys)
    assert profile_fingerprint(first) != profile_fingerprint(reversed_values)
