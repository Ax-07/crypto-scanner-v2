"""Définit et valide la configuration métier transmise à un job de scan."""

from __future__ import annotations

import math
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator, model_validator

Timeframe = Literal[
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
]
PROJECT_TIMEFRAMES: tuple[str, ...] = get_args(Timeframe)
MacdSignal = Literal["bullish", "bearish", "neutral"]
BollingerPosition = Literal["oversold", "near_oversold", "neutral", "near_overbought", "overbought"]
StochasticSignal = Literal["oversold", "overbought", "bullish_cross", "bearish_cross", "neutral"]


def default_ma_timeframes() -> list[Timeframe]:
    """Retourne une nouvelle liste des timeframes MA par défaut."""
    return ["1w", "1d", "4h"]


def default_confluence_weights() -> dict[str, float]:
    """Retourne une nouvelle table des poids de confluence par défaut."""
    return {
        "rsi": 20.0,
        "trend": 25.0,
        "macd": 20.0,
        "bollinger": 20.0,
        "stochastic": 15.0,
    }


class MarketIndicatorConfig(BaseModel):
    """Profil technique reproductible partagé par le scanner et le marché."""

    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_threshold: float = Field(default=35, ge=0, le=100)
    use_rsi: bool = True
    use_ma: bool = True
    use_sma: bool = True
    use_ema: bool = True
    sma_periods: list[int] = Field(default_factory=lambda: [20, 50])
    ema_periods: list[int] = Field(default_factory=lambda: [20, 50])
    macd_fast_period: int = Field(default=12, ge=2, le=100)
    macd_slow_period: int = Field(default=26, ge=3, le=200)
    macd_signal_period: int = Field(default=9, ge=2, le=100)
    use_macd: bool = True
    bollinger_period: int = Field(default=20, ge=2, le=200)
    bollinger_std_dev: float = Field(default=2.0, gt=0, le=10)
    use_bollinger: bool = True
    stochastic_k_period: int = Field(default=14, ge=2, le=200)
    stochastic_d_period: int = Field(default=3, ge=2, le=50)
    stochastic_oversold: float = Field(default=20, ge=0, le=100)
    stochastic_overbought: float = Field(default=80, ge=0, le=100)
    use_stochastic: bool = True
    use_confluence_score: bool = True
    confluence_weights: dict[str, float] = Field(default_factory=default_confluence_weights)
    origin: Literal["default", "scan", "custom"] = "default"

    @field_validator("sma_periods", "ema_periods")
    @classmethod
    def validate_profile_periods(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("les périodes ne doivent pas contenir de doublons")
        cleaned = sorted(value)
        if not cleaned or any(period < 2 or period > 1000 for period in cleaned):
            raise ValueError("les périodes doivent être comprises entre 2 et 1000")
        return cleaned

    @field_validator("confluence_weights")
    @classmethod
    def validate_profile_weights(cls, value: dict[str, float]) -> dict[str, float]:
        normalized = {name: float(weight) for name, weight in value.items()}
        if any(not math.isfinite(weight) or weight < 0 for weight in normalized.values()):
            raise ValueError("les pondérations doivent être finies et positives ou nulles")
        return normalized

    @model_validator(mode="after")
    def validate_profile(self) -> "MarketIndicatorConfig":
        if self.macd_fast_period >= self.macd_slow_period:
            raise ValueError("macd_fast_period doit être inférieur à macd_slow_period")
        if self.stochastic_oversold >= self.stochastic_overbought:
            raise ValueError("stochastic_oversold doit être inférieur à stochastic_overbought")
        if self.use_ma and not (self.use_sma or self.use_ema):
            raise ValueError("use_ma nécessite SMA ou EMA")
        return self

    @classmethod
    def from_scan(cls, config: "ScanConfig") -> "MarketIndicatorConfig":
        names = set(cls.model_fields) - {"origin"}
        values = config.model_dump(include=names)
        return cls(**values, origin="scan")


class ScanConfig(BaseModel):
    """Configuration validée d'un scan, indépendante des autres jobs.

    Les validateurs normalisent l'exchange et la devise, contrôlent les
    périodes, puis vérifient les dépendances entre indicateurs et filtres.
    """

    exchange_id: str = Field(default="binance", description="Identifiant de classe CCXT.")
    market_type: Literal["spot", "swap", "future"] = Field(
        default="spot", description="Type exact de marché CCXT à scanner."
    )
    quote: str = Field(default="USDC", description="Devise de cotation, normalisée en majuscules.")
    exclude_stable_pairs: bool = True
    max_pairs: int | None = Field(default=None, ge=1, le=2000)

    timeframe: Timeframe = Field(default="4h", description="Timeframe principal du scan.")
    min_ohlcv_bars: int = Field(
        default=200, ge=60, le=1500, description="Minimum de bougies OHLCV demandé."
    )
    max_concurrency: int = Field(
        default=6, ge=1, le=20, description="Nombre maximal d'analyses de symboles simultanées."
    )
    max_retries: int = Field(default=3, ge=0, le=8)
    retry_delay_seconds: float = Field(
        default=1.5, ge=0.1, le=30, description="Délai initial du backoff, en secondes."
    )

    use_rsi: bool = True
    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_threshold: float = Field(default=35, ge=0, le=100)

    use_ma: bool = True
    use_sma: bool = True
    use_ema: bool = True
    sma_periods: list[int] = Field(default_factory=lambda: [20, 50])
    ema_periods: list[int] = Field(default_factory=lambda: [20, 50])
    ma_timeframes: list[Timeframe] = Field(default_factory=default_ma_timeframes)
    min_trend_score: int = Field(default=2, ge=0, le=20)

    use_macd: bool = True
    macd_fast_period: int = Field(default=12, ge=2, le=100)
    macd_slow_period: int = Field(default=26, ge=3, le=200)
    macd_signal_period: int = Field(default=9, ge=2, le=100)

    use_bollinger: bool = True
    bollinger_period: int = Field(default=20, ge=2, le=200)
    bollinger_std_dev: float = Field(default=2.0, gt=0, le=10)

    use_stochastic: bool = True
    stochastic_k_period: int = Field(default=14, ge=2, le=200)
    stochastic_d_period: int = Field(default=3, ge=2, le=50)
    stochastic_oversold: float = Field(default=20, ge=0, le=100)
    stochastic_overbought: float = Field(default=80, ge=0, le=100)

    use_confluence_score: bool = True
    min_confluence_score: float = Field(default=60, ge=0, le=100)
    confluence_weights: dict[str, float] = Field(
        default_factory=default_confluence_weights,
        description="Poids non négatifs renormalisés sur les indicateurs actifs et calculables.",
    )

    filter_macd_signal: list[MacdSignal] | None = None
    filter_bb_position: list[BollingerPosition] | None = None
    filter_stoch_signal: list[StochasticSignal] | None = None

    @field_validator("quote")
    @classmethod
    def normalize_quote(cls, value: str) -> str:
        """Normalise la quote et rejette les identifiants vides ou non alphanumériques."""
        value = value.strip().upper()
        if not value or not value.isalnum():
            raise ValueError("quote doit être une devise valide, par exemple USDC")
        return value

    @field_validator("exchange_id")
    @classmethod
    def normalize_exchange_id(cls, value: str) -> str:
        """Normalise l'identifiant CCXT en minuscules et impose une valeur."""
        value = value.strip().lower()
        if not value:
            raise ValueError("exchange_id est obligatoire")
        return value

    @field_validator("sma_periods", "ema_periods")
    @classmethod
    def validate_periods(cls, value: list[int]) -> list[int]:
        """Trie les périodes MA et impose unicité et bornes de 2 à 1000."""
        if len(value) != len(set(value)):
            raise ValueError("les périodes ne doivent pas contenir de doublons")
        cleaned = sorted(value)
        if not cleaned or any(period < 2 or period > 1000 for period in cleaned):
            raise ValueError("les périodes doivent être comprises entre 2 et 1000")
        return cleaned

    @field_validator("ma_timeframes")
    @classmethod
    def validate_ma_timeframes(cls, value: list[Timeframe]) -> list[Timeframe]:
        """Rejette les timeframes MA dupliqués sans modifier leur ordre."""
        if len(value) != len(set(value)):
            raise ValueError("les timeframes MA ne doivent pas contenir de doublons")
        return value

    @field_validator("filter_macd_signal", "filter_bb_position", "filter_stoch_signal")
    @classmethod
    def deduplicate_filters(cls, value: list[str] | None) -> list[str] | None:
        """Déduplique un filtre de signaux en conservant son ordre."""
        return list(dict.fromkeys(value)) if value else value

    @field_validator("confluence_weights")
    @classmethod
    def validate_weights(cls, value: dict[str, float]) -> dict[str, float]:
        """Convertit les poids en nombres finis positifs ou nuls."""
        normalized = {name: float(weight) for name, weight in value.items()}
        if any(not math.isfinite(weight) or weight < 0 for weight in normalized.values()):
            raise ValueError("les pondérations doivent être finies et positives ou nulles")
        return normalized

    @model_validator(mode="after")
    def validate_consistency(self) -> "ScanConfig":
        """Vérifie les relations entre périodes, seuils et indicateurs actifs.

        Returns:
            Configuration entièrement validée.

        Raises:
            ValueError: Si deux paramètres forment une combinaison incohérente.
        """
        if self.macd_fast_period >= self.macd_slow_period:
            raise ValueError("macd_fast_period doit être inférieur à macd_slow_period")
        if self.stochastic_oversold >= self.stochastic_overbought:
            raise ValueError("stochastic_oversold doit être inférieur à stochastic_overbought")
        if self.use_ma and not (self.use_sma or self.use_ema):
            raise ValueError("USE_MA nécessite au moins SMA ou EMA")
        if self.min_trend_score > len(self.ma_timeframes):
            raise ValueError("min_trend_score ne peut pas dépasser le nombre de timeframes MA")

        expected = {"rsi", "trend", "macd", "bollinger", "stochastic"}
        unknown = set(self.confluence_weights) - expected
        if unknown:
            raise ValueError(f"pondérations inconnues: {sorted(unknown)}")
        active = {
            "rsi": self.use_rsi,
            "trend": self.use_ma,
            "macd": self.use_macd,
            "bollinger": self.use_bollinger,
            "stochastic": self.use_stochastic,
        }
        if self.use_confluence_score and not any(
            active[name] and self.confluence_weights.get(name, 0) > 0 for name in active
        ):
            raise ValueError(
                "la confluence nécessite une pondération positive pour un indicateur actif"
            )
        return self
