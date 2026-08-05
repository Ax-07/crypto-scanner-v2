from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.candles import Candle
from app.domain.ohlcv_fingerprint import (
    aggregate_input_fingerprints,
    fingerprint_ohlcv_stream,
)


def candle(open_time: int = 1_700_000_000_000, **changes: object) -> Candle:
    values: dict[str, object] = {
        "exchange_id": "binance",
        "market_type": "spot",
        "symbol": "BTC/USDC",
        "timeframe": "1m",
        "open_time": open_time,
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 42.0,
        "close_time": open_time + 60_000,
        "is_closed": True,
    }
    values.update(changes)
    return Candle(**values)  # type: ignore[arg-type]


def stream(rows: list[Candle], **changes: object):
    values: dict[str, object] = {
        "role": "primary",
        "exchange_id": "binance",
        "market_type": "spot",
        "symbol": "BTC/USDC",
        "timeframe": "1m",
        "requested_start_ms": 1_700_000_000_000,
        "requested_end_ms": 1_700_000_180_000,
        "closed_only": True,
        "warmup_bars": 1,
        "future_bars": 1,
        "gaps_validated": True,
    }
    values.update(changes)
    return fingerprint_ohlcv_stream(rows, **values)  # type: ignore[arg-type]


def test_identical_logical_instances_have_identical_hashes_and_negative_zero_is_normalized() -> (
    None
):
    first = stream([candle(open=-0.0)])
    second = stream([candle(open=0.0)])
    assert first == second
    assert first.fingerprint == (
        "sha256:7439f766ad27319ee757422e6c18aad6f386bd9ca2f2d5ac6e9974ee692949b4"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("open_time", 1_700_000_000_001),
        ("open", 100.1),
        ("high", 102.1),
        ("low", 98.9),
        ("close", 101.1),
        ("volume", 43.0),
        ("close_time", 1_700_000_060_001),
        ("is_closed", False),
    ],
)
def test_each_consumed_candle_field_changes_hash(field: str, value: object) -> None:
    base = candle()
    changed = replace(base, **{field: value})
    assert (
        stream([base], closed_only=False).fingerprint
        != stream([changed], closed_only=False).fingerprint
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_ohlcv_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="non finies"):
        stream([candle(close=value)])


def test_unsorted_and_duplicate_timestamps_are_rejected() -> None:
    first = candle()
    second = candle(first.open_time + 60_000)
    with pytest.raises(ValueError, match="strictement croissants"):
        stream([second, first])
    with pytest.raises(ValueError, match="strictement croissants"):
        stream([first, first])


@pytest.mark.parametrize(
    "metadata",
    [
        {"role": "trend:4h"},
        {"symbol": "ETH/USDC"},
        {"timeframe": "5m"},
        {"exchange_id": "kraken"},
        {"market_type": "swap"},
    ],
)
def test_stream_metadata_changes_hash(metadata: dict[str, object]) -> None:
    rows = (
        [candle(**metadata)]
        if set(metadata)
        <= {
            "symbol",
            "timeframe",
            "exchange_id",
            "market_type",
        }
        else [candle()]
    )
    assert stream([candle()]).fingerprint != stream(rows, **metadata).fingerprint


def test_aggregate_order_is_canonical_and_covers_source_identity_and_secondary_stream() -> None:
    primary = stream([candle()])
    trend_candle = candle(timeframe="4h", close_time=1_700_014_400_000)
    trend = stream(
        [trend_candle],
        role="trend:4h",
        timeframe="4h",
        warmup_bars=60,
        future_bars=0,
    )
    first = aggregate_input_fingerprints("sha256:" + "a" * 64, [primary, trend])
    reordered = aggregate_input_fingerprints("sha256:" + "a" * 64, [trend, primary])
    changed_source = aggregate_input_fingerprints("sha256:" + "b" * 64, [primary, trend])
    changed_trend = aggregate_input_fingerprints(
        "sha256:" + "a" * 64,
        [primary, trend.model_copy(update={"fingerprint": "sha256:" + "c" * 64})],
    )
    assert first == reordered
    assert first.input_data_fingerprint != changed_source.input_data_fingerprint
    assert first.input_data_fingerprint != changed_trend.input_data_fingerprint


def test_duplicate_stream_identity_is_rejected() -> None:
    primary = stream([candle()])
    with pytest.raises(ValueError, match="même identité"):
        aggregate_input_fingerprints("source", [primary, primary])
