"""Normalisation des bougies CCXT et sélection des bougies clôturées."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import pandas as pd
from app.core.settings import PROJECT_TIMEFRAMES

OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
TIMEFRAME_SECONDS: dict[str, int] = dict(
    zip(
        PROJECT_TIMEFRAMES,
        (
            60,
            180,
            300,
            900,
            1_800,
            3_600,
            7_200,
            14_400,
            21_600,
            28_800,
            43_200,
            86_400,
            259_200,
            604_800,
        ),
        strict=True,
    )
)


@dataclass(frozen=True, slots=True)
class Candle:
    """Représentation canonique d'une bougie brute persistée.

    Tous les temps sont des timestamps Unix en millisecondes, comme les lignes
    CCXT. ``close_time`` est la fin exclusive de l'intervalle lorsqu'elle est
    connue.
    """

    exchange_id: str
    market_type: str
    symbol: str
    timeframe: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int | None = None
    is_closed: bool = True

    def to_ohlcv(self) -> list[float | int]:
        """Convertit la bougie vers le format à six colonnes attendu par CCXT."""
        return [self.open_time, self.open, self.high, self.low, self.close, self.volume]

    def to_chart(self) -> dict[str, float | int | bool]:
        """Convertit la bougie vers le contrat historique du graphique."""
        return {
            "time": timestamp_ms_to_chart_seconds(self.open_time),
            "open_time": self.open_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "is_closed": self.is_closed,
        }


def timeframe_seconds(timeframe: str) -> int:
    """Convertit un timeframe pris en charge en durée exprimée en secondes.

    Raises:
        ValueError: Si le timeframe ne figure pas dans ``TIMEFRAME_SECONDS``.
    """
    try:
        return TIMEFRAME_SECONDS[timeframe]
    except KeyError as exc:
        raise ValueError(f"Timeframe non pris en charge: {timeframe}") from exc


def timeframe_milliseconds(timeframe: str) -> int:
    """Convertit un timeframe pris en charge en millisecondes."""
    return timeframe_seconds(timeframe) * 1_000


def is_candle_closed(open_time: int, timeframe: str, now_ms: int) -> bool:
    """Détermine purement si l'intervalle d'une bougie est entièrement écoulé."""
    return open_time + timeframe_milliseconds(timeframe) <= now_ms


def candle_from_ohlcv(
    row: Sequence[Any],
    *,
    exchange_id: str,
    market_type: str,
    symbol: str,
    timeframe: str,
    now_ms: int,
) -> Candle:
    """Valide une ligne CCXT et construit une bougie canonique.

    Raises:
        ValueError: Si la ligne ne contient pas six nombres finis.
    """
    if len(row) < 6:
        raise ValueError("Une ligne OHLCV doit contenir au moins six valeurs")
    values = [float(value) for value in row[:6]]
    if not all(math.isfinite(value) for value in values[:5]):
        raise ValueError("Timestamp ou valeur OHLC non finie")
    volume = values[5] if math.isfinite(values[5]) else 0.0
    open_time = int(values[0])
    interval = timeframe_milliseconds(timeframe)
    return Candle(
        exchange_id=exchange_id,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        open=values[1],
        high=values[2],
        low=values[3],
        close=values[4],
        volume=volume,
        close_time=open_time + interval,
        is_closed=is_candle_closed(open_time, timeframe, now_ms),
    )


def candles_to_frame(candles: Iterable[Candle]) -> pd.DataFrame:
    """Convertit des bougies typées vers le DataFrame historique du domaine."""
    return rows_to_frame(candle.to_ohlcv() for candle in candles)


def find_missing_ranges(
    open_times: Iterable[int],
    timeframe: str,
    *,
    now_ms: int,
    max_ranges: int | None = None,
) -> list[tuple[int, int]]:
    """Détecte les trous internes sous forme de plages ``[début, fin)``.

    Le début de cotation n'est jamais inventé : seules les discontinuités entre
    deux bougies connues sont rapportées. Les intervalles futurs sont ignorés.
    """
    interval = timeframe_milliseconds(timeframe)
    times = sorted({int(value) for value in open_times if int(value) <= now_ms})
    missing: list[tuple[int, int]] = []
    for previous, current in zip(times, times[1:]):
        expected = previous + interval
        if current > expected:
            end = min(current, now_ms + 1)
            if expected < end:
                missing.append((expected, end))
                if max_ranges is not None and len(missing) >= max_ranges:
                    break
    return missing


def timestamp_ms_to_utc(timestamp_ms: float | int) -> datetime:
    """Convertit un timestamp CCXT en millisecondes en datetime UTC."""
    return datetime.fromtimestamp(float(timestamp_ms) / 1_000, tz=timezone.utc)


def timestamp_ms_to_chart_seconds(timestamp_ms: float | int) -> int:
    """Convertit les millisecondes CCXT en secondes entières pour le graphique."""
    return int(float(timestamp_ms) // 1_000)


def rows_to_frame(rows: Iterable[Sequence[Any]]) -> pd.DataFrame:
    """Normalise des lignes CCXT et écarte les valeurs timestamp/OHLC invalides.

    Le volume invalide devient zéro. Les colonnes ``timestamp`` (millisecondes)
    et ``time`` (datetime UTC) sont toutes deux conservées.
    """
    frame = pd.DataFrame(list(rows), columns=OHLCV_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=("timestamp", "time", *OHLCV_COLUMNS[1:]))
    for column in OHLCV_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    required = frame[["timestamp", "open", "high", "low", "close"]]
    finite = required.map(lambda value: pd.notna(value) and math.isfinite(value)).all(axis=1)
    frame = frame.loc[finite].copy()
    frame["volume"] = frame["volume"].where(
        frame["volume"].map(lambda value: pd.notna(value) and math.isfinite(value)), 0.0
    )
    frame["time"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    return frame[["timestamp", "time", "open", "high", "low", "close", "volume"]].reset_index(
        drop=True
    )


def closed_candles(
    frame: pd.DataFrame, timeframe: str, *, now_ms: int | None = None
) -> pd.DataFrame:
    """Retourne les bougies dont la durée complète est écoulée.

    Une bougie est clôturée lorsque ``timestamp + durée <= now_ms``. Le
    DataFrame retourné est une copie afin de préserver l'entrée.
    """
    if frame is None or frame.empty:
        return frame.copy() if frame is not None else frame
    current_ms = (
        now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1_000)
    )
    return frame.loc[frame["timestamp"] + timeframe_seconds(timeframe) * 1_000 <= current_ms].copy()
