"""Fingerprint cryptographique versionné des entrées OHLCV d'un backtest."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.candles import Candle

OHLCV_FINGERPRINT_VERSION: Final = "ohlcv-content-sha256-v1"
OHLCV_AGGREGATE_FINGERPRINT_VERSION: Final = "ohlcv-input-aggregate-sha256-v1"


def _sha256(value: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("fingerprint doit être un SHA-256 préfixé")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError("fingerprint doit être un SHA-256 hexadécimal") from exc
    if value[7:] != value[7:].lower():
        raise ValueError("fingerprint SHA-256 doit être en minuscules")
    return value


def _text(digest: object, value: str) -> None:
    encoded = value.encode("utf-8")
    if len(encoded) > 2**32 - 1:
        raise ValueError("champ texte trop long pour l'encodage OHLCV")
    digest.update(struct.pack(">I", len(encoded)))  # type: ignore[attr-defined]
    digest.update(encoded)  # type: ignore[attr-defined]


def _integer(digest: object, value: int) -> None:
    digest.update(struct.pack(">q", value))  # type: ignore[attr-defined]


def _optional_integer(digest: object, value: int | None) -> None:
    digest.update(b"\x00" if value is None else b"\x01")  # type: ignore[attr-defined]
    if value is not None:
        _integer(digest, value)


def _number(digest: object, value: float) -> None:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("les valeurs OHLCV non finies sont interdites")
    if number == 0.0:
        number = 0.0
    digest.update(struct.pack(">d", number))  # type: ignore[attr-defined]


class InputDataStreamFingerprint(BaseModel):
    """Métadonnées et SHA-256 d'un flux OHLCV effectivement chargé."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint_version: Literal["ohlcv-content-sha256-v1"] = OHLCV_FINGERPRINT_VERSION
    role: str = Field(min_length=1)
    exchange_id: str = Field(min_length=1)
    market_type: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    requested_start_ms: int
    requested_end_ms: int
    effective_first_open_time_ms: int | None = None
    effective_last_open_time_ms: int | None = None
    candle_count: int = Field(ge=0)
    closed_only: bool = True
    warmup_bars: int = Field(ge=0)
    future_bars: int = Field(ge=0)
    gaps_validated: bool
    fingerprint: str

    @field_validator("fingerprint")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        return _sha256(value)

    @model_validator(mode="after")
    def validate_bounds(self) -> "InputDataStreamFingerprint":
        if self.requested_start_ms >= self.requested_end_ms:
            raise ValueError("requested_start_ms doit précéder requested_end_ms")
        if self.candle_count == 0:
            if (
                self.effective_first_open_time_ms is not None
                or self.effective_last_open_time_ms is not None
            ):
                raise ValueError("un flux vide ne possède pas de bornes effectives")
        elif (
            self.effective_first_open_time_ms is None
            or self.effective_last_open_time_ms is None
            or self.effective_first_open_time_ms > self.effective_last_open_time_ms
        ):
            raise ValueError("les bornes effectives du flux sont invalides")
        return self

    def sort_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.role,
            self.exchange_id,
            self.market_type,
            self.symbol,
            self.timeframe,
        )


class BacktestInputFingerprint(BaseModel):
    """Fingerprint agrégé et inventaire reproductible des flux d'un source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint_version: Literal["ohlcv-input-aggregate-sha256-v1"] = (
        OHLCV_AGGREGATE_FINGERPRINT_VERSION
    )
    source_identity: str = Field(min_length=1)
    input_data_fingerprint: str
    streams: tuple[InputDataStreamFingerprint, ...] = Field(min_length=1)

    _validate_sha256 = field_validator("input_data_fingerprint")(_sha256)

    @model_validator(mode="after")
    def validate_stream_order(self) -> "BacktestInputFingerprint":
        keys = [stream.sort_key() for stream in self.streams]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("les flux doivent être uniques et ordonnés canoniquement")
        return self


class PersistedBacktestInputFingerprint(BaseModel):
    """Provenance attendue d'un job et état de confirmation par le moteur."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    fingerprint: BacktestInputFingerprint
    confirmed_at_ms: int | None = None


def fingerprint_ohlcv_stream(
    candles: Sequence[Candle],
    *,
    role: str,
    exchange_id: str,
    market_type: str,
    symbol: str,
    timeframe: str,
    requested_start_ms: int,
    requested_end_ms: int,
    closed_only: bool,
    warmup_bars: int,
    future_bars: int,
    gaps_validated: bool,
) -> InputDataStreamFingerprint:
    """Hache un flux en IEEE-754 binaire big-endian, sans copie sérialisée."""
    if requested_start_ms >= requested_end_ms:
        raise ValueError("la fenêtre demandée du flux est invalide")
    previous: int | None = None
    digest = hashlib.sha256()
    digest.update(b"scanner-binance:ohlcv-stream\x00")
    for value in (
        OHLCV_FINGERPRINT_VERSION,
        role,
        exchange_id,
        market_type,
        symbol,
        timeframe,
    ):
        _text(digest, value)
    digest.update(b"\x01" if closed_only else b"\x00")
    _integer(digest, requested_start_ms)
    _integer(digest, requested_end_ms)
    _integer(digest, warmup_bars)
    _integer(digest, future_bars)
    _integer(digest, len(candles))
    _optional_integer(digest, candles[0].open_time if candles else None)
    _optional_integer(digest, candles[-1].open_time if candles else None)

    for candle in candles:
        if previous is not None and candle.open_time <= previous:
            raise ValueError("les timestamps OHLCV doivent être strictement croissants")
        if (
            candle.exchange_id != exchange_id
            or candle.market_type != market_type
            or candle.symbol != symbol
            or candle.timeframe != timeframe
        ):
            raise ValueError("une bougie ne correspond pas aux métadonnées de son flux")
        if closed_only and not candle.is_closed:
            raise ValueError("un flux closed_only contient une bougie ouverte")
        _integer(digest, candle.open_time)
        for number in (candle.open, candle.high, candle.low, candle.close, candle.volume):
            _number(digest, number)
        _optional_integer(digest, candle.close_time)
        digest.update(b"\x01" if candle.is_closed else b"\x00")
        previous = candle.open_time

    return InputDataStreamFingerprint(
        role=role,
        exchange_id=exchange_id,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        requested_start_ms=requested_start_ms,
        requested_end_ms=requested_end_ms,
        effective_first_open_time_ms=candles[0].open_time if candles else None,
        effective_last_open_time_ms=candles[-1].open_time if candles else None,
        candle_count=len(candles),
        closed_only=closed_only,
        warmup_bars=warmup_bars,
        future_bars=future_bars,
        gaps_validated=gaps_validated,
        fingerprint="sha256:" + digest.hexdigest(),
    )


def aggregate_input_fingerprints(
    source_identity: str,
    streams: Sequence[InputDataStreamFingerprint],
) -> BacktestInputFingerprint:
    """Agrège les flux dans un ordre indépendant des requêtes et dictionnaires."""
    ordered = tuple(sorted(streams, key=lambda item: item.sort_key()))
    if not ordered:
        raise ValueError("au moins un flux OHLCV est requis")
    if len({item.sort_key() for item in ordered}) != len(ordered):
        raise ValueError("plusieurs flux possèdent la même identité canonique")
    digest = hashlib.sha256()
    digest.update(b"scanner-binance:ohlcv-aggregate\x00")
    _text(digest, OHLCV_AGGREGATE_FINGERPRINT_VERSION)
    _text(digest, source_identity)
    _integer(digest, len(ordered))
    for stream in ordered:
        for value in (*stream.sort_key(), stream.fingerprint_version, stream.fingerprint):
            _text(digest, value)
        _integer(digest, stream.requested_start_ms)
        _integer(digest, stream.requested_end_ms)
        _optional_integer(digest, stream.effective_first_open_time_ms)
        _optional_integer(digest, stream.effective_last_open_time_ms)
        _integer(digest, stream.candle_count)
        _integer(digest, stream.warmup_bars)
        _integer(digest, stream.future_bars)
        digest.update(b"\x01" if stream.closed_only else b"\x00")
        digest.update(b"\x01" if stream.gaps_validated else b"\x00")
    return BacktestInputFingerprint(
        source_identity=source_identity,
        input_data_fingerprint="sha256:" + digest.hexdigest(),
        streams=ordered,
    )
