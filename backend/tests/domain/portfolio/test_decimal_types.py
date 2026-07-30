from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.portfolio import (
    PortfolioSimulationConfig,
    PortfolioSimulationStep,
    PortfolioValidationError,
    PositionSizingMode,
    require_non_negative_decimal,
    require_positive_decimal,
    to_finite_decimal,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, Decimal("1")),
        ("1.25", Decimal("1.25")),
        (0.1, Decimal("0.1")),
        (Decimal("2.5"), Decimal("2.5")),
        ("1e-100", Decimal("1e-100")),
        ("9e100", Decimal("9e100")),
    ],
)
def test_safe_decimal_conversion(value: object, expected: Decimal) -> None:
    assert to_finite_decimal(value, name="value") == expected  # type: ignore[arg-type]


def test_float_is_converted_through_its_text_representation() -> None:
    assert to_finite_decimal(0.1, name="value") == Decimal("0.1")
    assert to_finite_decimal(0.1, name="value") != Decimal(0.1)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "abc", None, True])
def test_invalid_or_non_finite_decimals_are_rejected(value: object) -> None:
    with pytest.raises(PortfolioValidationError):
        to_finite_decimal(value, name="value")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, "-1"])
def test_positive_decimal_rejects_zero_and_negative(value: object) -> None:
    with pytest.raises(PortfolioValidationError):
        require_positive_decimal(value, name="value")  # type: ignore[arg-type]


def test_non_negative_decimal_accepts_zero_and_rejects_negative() -> None:
    assert require_non_negative_decimal(0, name="value") == Decimal("0")
    with pytest.raises(PortfolioValidationError):
        require_non_negative_decimal("-0.01", name="value")


@pytest.mark.parametrize(
    "updates",
    [
        {"version": 2},
        {"quote_asset": "  "},
        {"initial_capital": Decimal("0")},
        {"initial_capital": Decimal("NaN")},
        {"position_size_percent": Decimal("0")},
        {"position_size_percent": Decimal("100.1")},
        {"fee_rate": Decimal("-0.1")},
        {"fee_rate": Decimal("1")},
        {"slippage_rate": Decimal("Infinity")},
        {"slippage_rate": Decimal("1")},
        {"position_sizing_mode": "unknown"},
        {"execution_policy": "unknown"},
        {"end_of_test_policy": "unknown"},
    ],
)
def test_configuration_rejects_invalid_values(updates: dict[str, object]) -> None:
    values: dict[str, object] = {"quote_asset": "USDC"}
    values.update(updates)
    with pytest.raises(PortfolioValidationError):
        PortfolioSimulationConfig(**values)  # type: ignore[arg-type]


def test_configuration_normalizes_supported_values() -> None:
    config = PortfolioSimulationConfig(
        quote_asset=" USDC ",
        initial_capital="1000",  # type: ignore[arg-type]
        position_sizing_mode="percent_cash",  # type: ignore[arg-type]
        position_size_percent=50.0,  # type: ignore[arg-type]
        fee_rate="0.01",  # type: ignore[arg-type]
    )
    assert config.quote_asset == "USDC"
    assert config.initial_capital == Decimal("1000")
    assert config.position_sizing_mode is PositionSizingMode.PERCENT_CASH
    assert config.position_size_percent == Decimal("50.0")


def test_step_requires_aware_ordered_timestamps_and_positive_prices() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(PortfolioValidationError):
        PortfolioSimulationStep("obs", now, now, Decimal("1"), Decimal("1"), True)
    with pytest.raises(PortfolioValidationError):
        PortfolioSimulationStep(
            "obs",
            now,
            now.replace(hour=1),
            Decimal("0"),
            Decimal("1"),
            True,
        )
