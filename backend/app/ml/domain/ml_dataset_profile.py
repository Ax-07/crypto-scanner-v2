"""Profils techniques reproductibles réservés aux datasets ML."""

from __future__ import annotations

from typing import Final, Literal

from app.core.settings import (
    AdxIndicatorConfig,
    AtrIndicatorConfig,
    DonchianIndicatorConfig,
    KeltnerIndicatorConfig,
    ScanConfig,
    SupertrendIndicatorConfig,
    Timeframe,
)

ML_DATASET_PROFILE_V2_ID: Final = "ml-dataset-v2"


def build_ml_dataset_profile_v2(
    *,
    timeframe: Timeframe,
    quote: str = "USDC",
    exchange_id: str = "binance",
    market_type: Literal["spot", "swap", "future"] = "spot",
) -> ScanConfig:
    """Construit le profil canonique d'observation du dataset ML v2.

    Les indicateurs historiques conservent exactement les valeurs par défaut
    de ScanConfig. Les extensions sont activées uniquement comme observations
    techniques et ne sont pas ajoutées au score de confluence historique.
    """
    return ScanConfig(
        timeframe=timeframe,
        quote=quote,
        exchange_id=exchange_id,
        market_type=market_type,
        atr=AtrIndicatorConfig(
            enabled=True,
        ),
        adx=AdxIndicatorConfig(
            enabled=True,
        ),
        supertrend=SupertrendIndicatorConfig(
            enabled=True,
        ),
        donchian=DonchianIndicatorConfig(
            enabled=True,
        ),
        keltner=KeltnerIndicatorConfig(
            enabled=True,
        ),
    )
