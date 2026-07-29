from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.scanner import ScanResult


def test_scan_result_serialization_keeps_existing_public_shape() -> None:
    payload = ScanResult(
        symbol="BTC/USDC",
        timeframe="4h",
        macd_signal_type="bullish",
        bb_position="near_oversold",
        stoch_signal="bullish_cross",
        confluence_grade="A+",
    ).model_dump(mode="json")
    assert payload["macd_signal_type"] == "bullish"
    assert payload["bb_position"] == "near_oversold"
    assert payload["stoch_signal"] == "bullish_cross"
    assert payload["confluence_grade"] == "A+"
    assert payload["rsi"] is None
    assert payload["trends"] == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("macd_signal_type", "up"),
        ("bb_position", "low"),
        ("stoch_signal", "cross"),
        ("confluence_grade", "S"),
    ],
)
def test_scan_result_rejects_unknown_runtime_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        ScanResult(symbol="BTC/USDC", timeframe="4h", **{field: value})


def test_openapi_exposes_literal_scanner_contracts() -> None:
    result = ScanResult.model_json_schema()["properties"]
    assert set(result["macd_signal_type"]["anyOf"][0]["enum"]) == {
        "bullish",
        "bearish",
        "neutral",
    }
    assert "null" in {item.get("type") for item in result["macd_signal_type"]["anyOf"]}
