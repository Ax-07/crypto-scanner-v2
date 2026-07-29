"""Tests du mode structuré de la confluence (Phase 3).

Couvre ``calculate_signal_factor``, ``calculate_trend_signal_factor`` et le
paramètre ``indicator_signals`` de ``calculate_confluence_score``: mapping des
nouveaux événements/états, règle de priorité structuré > historique, et
équivalence de score entre les deux modes sur des scénarios comparables.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.indicators import (
    IndicatorSignal,
    calculate_confluence_score,
    calculate_rsi_signal_factor,
    calculate_signal_factor,
    calculate_trend_signal_factor,
)


def _signal(
    *,
    status: str = "available",
    direction: str = "neutral",
    signal: str | None = None,
    state: str | None = None,
    strength: float = 0.5,
    reason: str | None = None,
    raw_value: float | None = None,
) -> IndicatorSignal:
    return IndicatorSignal(
        status=status,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        signal=signal,
        state=state,
        strength=strength,
        reason=reason,
        raw_value=raw_value,
    )


# ---------------------------------------------------------------------------
# calculate_signal_factor: nouveaux événements/états par indicateur
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state, expected",
    [
        ("oversold", 1.0),
        ("near_oversold", 0.75),
        ("neutral", 0.3),
        ("near_overbought", 0.0),
        ("overbought", 0.0),
    ],
)
def test_rsi_signal_factor_by_state(state: str, expected: float) -> None:
    signal = _signal(signal=state, state=state)
    assert calculate_signal_factor("rsi", signal) == expected


def test_rsi_signal_factor_exit_event_uses_state_not_event_name() -> None:
    # Un événement de sortie de zone (exit_oversold) porte l'état courant
    # (ex. neutral) dans "state": le facteur suit cet état, pas l'événement.
    signal = _signal(signal="exit_oversold", state="neutral", direction="bullish")
    assert calculate_signal_factor("rsi", signal) == 0.3


def test_rsi_signal_factor_unavailable_returns_none() -> None:
    signal = _signal(status="insufficient_data", state=None)
    assert calculate_signal_factor("rsi", signal) is None


# ---------------------------------------------------------------------------
# calculate_rsi_signal_factor: parité exacte avec le calcul historique,
# y compris dans les zones où "state" seul ne permet pas de distinguer les
# facteurs historiques (ex. RSI=45 vs RSI=55, tous deux "neutral").
# ---------------------------------------------------------------------------


def _legacy_rsi_factor(rsi_value: float, rsi_threshold: float) -> float:
    if rsi_value <= 30:
        return 1.0
    if rsi_value <= rsi_threshold:
        return 0.75
    if rsi_value < 50:
        return 0.3
    return 0.0


@pytest.mark.parametrize(
    "rsi_threshold, rsi_value",
    [
        (35, 20),
        (35, 30),
        (35, 30.01),
        (35, 34.99),
        (35, 35),
        (35, 35.01),
        (35, 49.99),
        (35, 50),
        (35, 55),
        (35, 70),
        (35, 80),
        (40, 30),
        (40, 35),
        (40, 40),
        (40, 40.01),
        (40, 49.99),
        (40, 50),
    ],
)
def test_calculate_rsi_signal_factor_matches_legacy(rsi_threshold: float, rsi_value: float) -> None:
    signal = _signal(raw_value=rsi_value)
    expected = _legacy_rsi_factor(rsi_value, rsi_threshold)
    assert calculate_rsi_signal_factor(signal, rsi_threshold=rsi_threshold) == expected


def test_calculate_rsi_signal_factor_unavailable_returns_none() -> None:
    signal = _signal(status="insufficient_data", raw_value=45.0)
    assert calculate_rsi_signal_factor(signal, rsi_threshold=35) is None


def test_calculate_rsi_signal_factor_missing_raw_value_returns_none() -> None:
    signal = _signal(raw_value=None)
    assert calculate_rsi_signal_factor(signal, rsi_threshold=35) is None


@pytest.mark.parametrize(
    "event, expected",
    [
        ("bullish_cross", 1.0),
        ("bullish_alignment", 1.0),
        ("price_above", 0.75),
        ("neutral", 0.5),
        ("price_below", 0.25),
        ("bearish_alignment", 0.0),
        ("bearish_cross", 0.0),
    ],
)
def test_moving_average_signal_factor(event: str, expected: float) -> None:
    signal = _signal(signal=event, state=None)
    assert calculate_signal_factor("sma", signal) == expected
    assert calculate_signal_factor("ema", signal) == expected


@pytest.mark.parametrize(
    "direction, expected",
    [("bullish", 1.0), ("neutral", 0.4), ("bearish", 0.0)],
)
def test_macd_signal_factor_uses_direction(direction: str, expected: float) -> None:
    signal = _signal(direction=direction, signal="bullish_cross", state="above_signal/above_zero")
    assert calculate_signal_factor("macd", signal) == expected


@pytest.mark.parametrize(
    "state, expected",
    [
        ("oversold", 1.0),
        ("near_oversold", 0.75),
        ("neutral", 0.35),
        ("near_overbought", 0.1),
        ("overbought", 0.0),
    ],
)
def test_bollinger_signal_factor_uses_state(state: str, expected: float) -> None:
    signal = _signal(signal="lower_band_breakout", state=state)
    assert calculate_signal_factor("bollinger", signal) == expected


@pytest.mark.parametrize(
    "event, expected",
    [
        ("bullish_cross", 1.0),
        ("oversold", 0.9),
        ("neutral", 0.35),
        ("bearish_cross", 0.1),
        ("overbought", 0.0),
    ],
)
def test_stochastic_signal_factor_uses_signal_event(event: str, expected: float) -> None:
    signal = _signal(signal=event, state="oversold")
    assert calculate_signal_factor("stochastic", signal) == expected


def test_calculate_trend_signal_factor_averages_sma_and_ema() -> None:
    sma = _signal(signal="bullish_cross")
    ema = _signal(signal="neutral")
    assert calculate_trend_signal_factor([sma, ema]) == pytest.approx((1.0 + 0.5) / 2)


def test_calculate_trend_signal_factor_ignores_unavailable() -> None:
    sma = _signal(status="insufficient_data", signal=None)
    ema = _signal(signal="bearish_cross")
    assert calculate_trend_signal_factor([sma, ema]) == 0.0


def test_calculate_trend_signal_factor_none_when_nothing_usable() -> None:
    sma = _signal(status="insufficient_data", signal=None)
    assert calculate_trend_signal_factor([sma]) is None


# ---------------------------------------------------------------------------
# calculate_confluence_score: mode structuré, priorité et équivalence legacy
# ---------------------------------------------------------------------------


_WEIGHTS: dict[str, float] = {
    "rsi": 20,
    "trend": 20,
    "macd": 20,
    "bollinger": 20,
    "stochastic": 20,
}


def _legacy_all_bullish() -> dict[str, Any]:
    return dict(
        rsi_value=25.0,
        rsi_threshold=35,
        trend_score=2,
        max_trend_score=2,
        macd_signal="bullish",
        bb_position="oversold",
        stoch_signal="bullish_cross",
        weights=_WEIGHTS,
    )


def test_structured_mode_matches_legacy_all_bullish() -> None:
    legacy_result = calculate_confluence_score(**_legacy_all_bullish())
    structured_signals = {
        "rsi": _signal(direction="bullish", signal="oversold", state="oversold", raw_value=25.0),
        "sma": _signal(direction="bullish", signal="bullish_cross"),
        "ema": _signal(direction="bullish", signal="bullish_cross"),
        "macd": _signal(direction="bullish"),
        "bollinger": _signal(direction="bullish", signal="lower_band_breakout", state="oversold"),
        "stochastic": _signal(direction="bullish", signal="bullish_cross", state="oversold"),
    }
    args = _legacy_all_bullish()
    structured_result = calculate_confluence_score(**args, indicator_signals=structured_signals)
    assert legacy_result is not None and structured_result is not None
    assert structured_result["score"] == legacy_result["score"]
    assert structured_result["grade"] == legacy_result["grade"]
    assert structured_result["breakdown"] == legacy_result["breakdown"]
    assert structured_result["effective_weights"] == legacy_result["effective_weights"]


def test_structured_mode_matches_legacy_all_neutral() -> None:
    legacy_args = dict(
        rsi_value=55.0,
        rsi_threshold=35,
        trend_score=1,
        max_trend_score=2,
        macd_signal="neutral",
        bb_position="neutral",
        stoch_signal="neutral",
        weights=_WEIGHTS,
    )
    legacy_result = calculate_confluence_score(**legacy_args)
    structured_signals = {
        "rsi": _signal(signal="near_overbought", state="near_overbought", raw_value=55.0),
        "sma": _signal(signal="neutral"),
        "ema": _signal(signal="neutral"),
        "macd": _signal(direction="neutral"),
        "bollinger": _signal(signal="lower_band_breakout", state="neutral"),
        "stochastic": _signal(signal="neutral", state="neutral"),
    }
    structured_result = calculate_confluence_score(
        **legacy_args, indicator_signals=structured_signals
    )
    assert legacy_result is not None and structured_result is not None
    assert structured_result["score"] == legacy_result["score"]
    assert structured_result["grade"] == legacy_result["grade"]


def test_structured_mode_matches_legacy_all_bearish() -> None:
    legacy_args = dict(
        rsi_value=90.0,
        rsi_threshold=35,
        trend_score=0,
        max_trend_score=2,
        macd_signal="bearish",
        bb_position="overbought",
        stoch_signal="overbought",
        weights=_WEIGHTS,
    )
    legacy_result = calculate_confluence_score(**legacy_args)
    structured_signals = {
        "rsi": _signal(signal="overbought", state="overbought", raw_value=90.0),
        "sma": _signal(signal="bearish_cross"),
        "ema": _signal(signal="bearish_cross"),
        "macd": _signal(direction="bearish"),
        "bollinger": _signal(signal="upper_band_breakout", state="overbought"),
        "stochastic": _signal(signal="overbought", state="overbought"),
    }
    structured_result = calculate_confluence_score(
        **legacy_args, indicator_signals=structured_signals
    )
    assert legacy_result is not None and structured_result is not None
    assert structured_result["score"] == legacy_result["score"]
    assert structured_result["grade"] == legacy_result["grade"]


def test_structured_key_present_but_unavailable_does_not_fallback_to_legacy() -> None:
    """Une clé structurée présente, même non disponible, l'emporte sur l'argument historique."""
    legacy_args = _legacy_all_bullish()
    structured_signals = {
        "rsi": _signal(status="insufficient_data", signal=None, state=None),
    }
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    assert "rsi" not in result["breakdown"]
    assert result["details"]["rsi"]["status"] == "insufficient_data"
    assert result["details"]["rsi"]["factor"] is None


def test_legacy_fallback_applies_when_structured_key_absent() -> None:
    legacy_args = _legacy_all_bullish()
    # Aucune clé "rsi" fournie: le fallback historique (rsi_value=25) reste actif.
    structured_signals = {
        "macd": _signal(direction="bullish"),
    }
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    assert "rsi" in result["breakdown"]
    assert result["details"]["rsi"]["factor"] == 1.0


def test_structured_conflict_with_legacy_uses_structured() -> None:
    legacy_args = _legacy_all_bullish()  # macd_signal="bullish" -> factor 1.0 historically
    structured_signals = {"macd": _signal(direction="bearish")}
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    assert result["details"]["macd"]["factor"] == 0.0


def test_sma_only_trend_signal() -> None:
    legacy_args = _legacy_all_bullish()
    structured_signals = {"sma": _signal(signal="bullish_alignment")}
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    assert result["details"]["trend"]["factor"] == 1.0


def test_ema_only_trend_signal() -> None:
    legacy_args = _legacy_all_bullish()
    structured_signals = {"ema": _signal(signal="bearish_cross")}
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    assert result["details"]["trend"]["factor"] == 0.0


def test_sma_ema_disagreement_averages_to_neutral_ish() -> None:
    legacy_args = _legacy_all_bullish()
    structured_signals = {
        "sma": _signal(signal="bullish_cross"),
        "ema": _signal(signal="bearish_cross"),
    }
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    assert result["details"]["trend"]["factor"] == pytest.approx(0.5)


def test_zero_weight_indicator_never_participates_in_structured_mode() -> None:
    legacy_args = _legacy_all_bullish()
    legacy_args["weights"] = {**_WEIGHTS, "rsi": 0}
    structured_signals = {"rsi": _signal(signal="oversold", state="oversold")}
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    assert "rsi" not in result["breakdown"]


def test_no_usable_weight_returns_none_in_structured_mode() -> None:
    result = calculate_confluence_score(
        rsi_value=None,
        rsi_threshold=35,
        trend_score=None,
        max_trend_score=0,
        macd_signal=None,
        bb_position=None,
        stoch_signal=None,
        weights={"rsi": 20},
        indicator_signals={"rsi": _signal(status="insufficient_data", signal=None, state=None)},
    )
    assert result is None


def test_mixed_structured_and_legacy_indicators() -> None:
    legacy_args = _legacy_all_bullish()
    structured_signals = {
        "rsi": _signal(signal="oversold", state="oversold"),
        "macd": _signal(direction="bullish"),
    }
    result = calculate_confluence_score(**legacy_args, indicator_signals=structured_signals)
    assert result is not None
    # bollinger/stochastic/trend restent sur l'argument historique (bullish partout).
    assert result["score"] == pytest.approx(100.0)
    assert result["grade"] == "A+"


@pytest.mark.parametrize(
    "score, expected_grade",
    [
        (90.0, "A+"),
        (89.99, "A"),
        (80.0, "A"),
        (79.99, "B"),
        (70.0, "B"),
        (69.99, "C"),
        (60.0, "C"),
        (59.99, "D"),
        (50.0, "D"),
        (49.99, "F"),
    ],
)
def test_grade_boundaries_unaffected_by_structured_mode(score: float, expected_grade: str) -> None:
    # Poids "trend" à 100%: le facteur legacy (trend_score/max_trend_score)
    # pilote directement le score final, structured mode non impliqué ici
    # (les bornes de grade sont indépendantes du mode d'entrée des facteurs).
    result = calculate_confluence_score(
        rsi_value=None,
        rsi_threshold=35,
        trend_score=score,
        max_trend_score=100,
        macd_signal=None,
        bb_position=None,
        stoch_signal=None,
        weights={"trend": 100},
    )
    assert result is not None
    assert result["grade"] == expected_grade
