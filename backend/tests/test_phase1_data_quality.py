from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app.core.settings import ScanConfig
from app.domain.analysis import AnalysisStatus
from app.services.market_stream import (
    build_indicator_event_markers,
    select_closed_ohlcv,
)
from app.services.scanner import ScannerService


def frame(size: int) -> pd.DataFrame:
    start = datetime.now(timezone.utc) - timedelta(hours=size + 2)
    timestamps = [(start + timedelta(hours=index)).timestamp() * 1_000 for index in range(size)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "time": pd.to_datetime(timestamps, unit="ms", utc=True),
            "open": [10.0] * size,
            "high": [11.0] * size,
            "low": [9.0] * size,
            "close": [10.0] * size,
            "volume": [1.0] * size,
        }
    )


def config(**changes: object) -> ScanConfig:
    values: dict[str, object] = {
        "timeframe": "1h",
        "min_ohlcv_bars": 60,
        "use_rsi": False,
        "use_ma": False,
        "use_macd": False,
        "use_bollinger": False,
        "use_stochastic": False,
        "use_confluence_score": False,
    }
    values.update(changes)
    return ScanConfig.model_validate(values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("count", "status"),
    [(59, AnalysisStatus.ERROR), (60, AnalysisStatus.SUCCESS), (61, AnalysisStatus.SUCCESS)],
)
async def test_min_ohlcv_bars_is_enforced_after_closed_selection(
    count: int, status: AnalysisStatus
) -> None:
    service = ScannerService(config())
    with patch("app.services.scanner.fetch_ohlcv", new=AsyncMock(return_value=frame(count))):
        outcome = await service.analyze_symbol(object(), "BTC/USDC")
    assert outcome.status is status
    if status is AnalysisStatus.ERROR:
        assert outcome.error and "59/60" in outcome.error


@pytest.mark.asyncio
async def test_indicator_requirement_and_minimum_form_one_final_requirement() -> None:
    service = ScannerService(
        config(
            min_ohlcv_bars=60,
            use_macd=True,
            macd_slow_period=55,
            macd_signal_period=10,
        )
    )
    with (
        patch("app.services.scanner.fetch_ohlcv", new=AsyncMock(return_value=frame(74))),
        patch("app.services.scanner.calculate_macd") as calculate,
    ):
        outcome = await service.analyze_symbol(object(), "NEW/USDC")
    assert outcome.status is AnalysisStatus.ERROR
    assert outcome.error and "74/75" in outcome.error
    calculate.assert_not_called()


def rows(*timestamps: int) -> list[list[float]]:
    return [[timestamp, 1, 2, 0, 1, 10] for timestamp in timestamps]


@pytest.mark.parametrize(
    ("history", "timeframe", "now_ms", "expected"),
    [
        (rows(), "1h", 3_600_000, []),
        (rows(0), "1h", 3_599_999, []),
        (rows(0), "1h", 3_600_000, [0]),
        (rows(0, 3_600_000), "1h", 7_199_999, [0]),
        (rows(0, 3_600_000), "1h", 7_200_000, [0, 3_600_000]),
        (rows(0, 300_000), "5m", 599_999, [0]),
    ],
)
def test_closed_bootstrap_selection_is_explicit_and_boundary_safe(
    history, timeframe: str, now_ms: int, expected: list[int]
) -> None:
    assert [row[0] for row in select_closed_ohlcv(history, timeframe, now_ms=now_ms)] == expected


def test_closed_selection_ignores_invalid_timestamp_without_dropping_last_closed() -> None:
    history: list[list[Any]] = [
        ["invalid", 1, 2, 0, 1, 10],
        *rows(0, 3_600_000),
    ]
    selected = select_closed_ohlcv(history, "1h", now_ms=7_200_000)
    assert [row[0] for row in selected] == [0, 3_600_000]


def test_markers_include_last_closed_candle_but_never_open_candle() -> None:
    """Un événement ne doit être produit que pour une bougie clôturée."""
    history = rows(0, 3_600_000)

    bundle = {
        "_ema_fast": pd.Series([0.0, 1.0], dtype=float),
        "_ema_slow": pd.Series([0.0, 0.0], dtype=float),
    }

    closed = select_closed_ohlcv(
        history,
        "1h",
        now_ms=7_200_000,
    )
    closed_frame = pd.DataFrame(
        {
            "timestamp": [row[0] for row in closed],
            "close": [row[4] for row in closed],
        }
    )

    markers = build_indicator_event_markers(
        closed_frame,
        bundle,
    )

    assert {marker["time"] for marker in markers} == {3_600}
    assert markers[0]["indicator"] == "ema"
    assert markers[0]["text"] == "EMA BUY"

    only_first = select_closed_ohlcv(
        history,
        "1h",
        now_ms=7_199_999,
    )
    open_excluded_frame = pd.DataFrame(
        {
            "timestamp": [row[0] for row in only_first],
            "close": [row[4] for row in only_first],
        }
    )

    assert (
        build_indicator_event_markers(
            open_excluded_frame,
            bundle,
        )
        == []
    )
