from __future__ import annotations

import csv
import io
import math
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.core.settings import ScanConfig
from app.domain.candles import closed_candles, rows_to_frame, timeframe_seconds
from app.domain.limits import primary_ohlcv_limit
from app.exporters.csv_exporter import CSV_COLUMNS, results_to_csv
from app.models.scanner import ScanResult


class ConfigTests(unittest.TestCase):
    def test_normalizes_identifiers_and_periods(self) -> None:
        config = ScanConfig(exchange_id=" BINANCE ", quote=" usdc ", sma_periods=[50, 20])
        self.assertEqual(config.exchange_id, "binance")
        self.assertEqual(config.quote, "USDC")
        self.assertEqual(config.sma_periods, [20, 50])

    def test_rejects_inconsistent_periods_thresholds_and_weights(self) -> None:
        invalid = (
            {"macd_fast_period": 30, "macd_slow_period": 20},
            {"stochastic_oversold": 80, "stochastic_overbought": 20},
            {"use_ma": True, "use_sma": False, "use_ema": False},
            {"confluence_weights": {"rsi": math.inf}},
            {"sma_periods": [20, 20]},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ScanConfig(**values)


class CandleTests(unittest.TestCase):
    def test_timeframe_duration(self) -> None:
        self.assertEqual(timeframe_seconds("4h"), 14_400)
        self.assertEqual(timeframe_seconds("1w"), 604_800)
        with self.assertRaises(ValueError):
            timeframe_seconds("2w")

    def test_only_open_last_candle_is_removed(self) -> None:
        now_ms = 1_800_000
        frame = rows_to_frame([[0, 1, 2, 0.5, 1.5, 10], [1_760_000, 2, 3, 1, 2.5, 11]])
        result = closed_candles(frame, "1m", now_ms=now_ms)
        self.assertEqual(result["timestamp"].tolist(), [0])

    def test_invalid_ohlc_is_dropped_and_invalid_volume_is_zero(self) -> None:
        frame = rows_to_frame([[0, 1, 2, 0.5, 1.5, math.inf], [60_000, 1, math.nan, 0.5, 1.5, 5]])
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["volume"], 0)


class LimitAndCsvTests(unittest.TestCase):
    def test_limit_only_uses_active_indicators(self) -> None:
        config = ScanConfig(
            min_ohlcv_bars=60,
            use_rsi=False,
            use_ma=False,
            use_macd=True,
            macd_slow_period=40,
            macd_signal_period=12,
            use_bollinger=False,
            use_stochastic=False,
            use_confluence_score=False,
        )
        self.assertEqual(primary_ohlcv_limit(config), 62)

    def test_csv_has_stable_columns_json_unicode_and_iso_date(self) -> None:
        result = ScanResult(
            symbol="ÉTH/USDC",
            timeframe="4h",
            last_close_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trends={"4h": True},
        )
        rows = list(csv.DictReader(io.StringIO(results_to_csv([result]))))
        self.assertEqual(list(rows[0]), CSV_COLUMNS)
        self.assertEqual(rows[0]["symbol"], "ÉTH/USDC")
        self.assertEqual(rows[0]["trends"], '{"4h": true}')
        self.assertIn("2026-01-01", rows[0]["last_close_time"])


if __name__ == "__main__":
    unittest.main()
