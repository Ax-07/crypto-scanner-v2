"""Primitives causales communes aux indicateurs fondés sur Wilder."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

__all__ = [
    "calculate_directional_movement",
    "calculate_true_range",
    "wilder_smoothing",
]


def _aligned_prices(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.DataFrame:
    """Aligne les prix sans muter les séries reçues."""
    return pd.concat(
        [
            high.astype(float).rename("high"),
            low.astype(float).rename("low"),
            close.astype(float).rename("close"),
        ],
        axis=1,
    )


def _valid_price_row(row: pd.Series) -> bool:
    values = (float(row["high"]), float(row["low"]), float(row["close"]))
    return all(math.isfinite(value) and value > 0 for value in values) and values[0] >= values[1]


def calculate_true_range(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """Calcule le True Range causal.

    La première valeur vaut ``high - low``. Ensuite le maximum de la plage et
    des deux gaps au close précédent est utilisé. Une ligne invalide produit
    ``NaN`` à cet index et ne peut donc pas devenir une valeur publique.
    """
    frame = _aligned_prices(high, low, close)
    result = pd.Series(np.nan, index=frame.index, dtype=float, name="true_range")
    previous_close: float | None = None
    for index, row in frame.iterrows():
        if not _valid_price_row(row):
            previous_close = None
            continue
        current_high = float(row["high"])
        current_low = float(row["low"])
        current_close = float(row["close"])
        value = current_high - current_low
        if previous_close is not None:
            value = max(
                value,
                abs(current_high - previous_close),
                abs(current_low - previous_close),
            )
        result.loc[index] = value
        previous_close = current_close
    return result


def calculate_directional_movement(
    high: pd.Series,
    low: pd.Series,
) -> dict[str, pd.Series]:
    """Calcule +DM/-DM, avec égalité neutralisée et première ligne nulle."""
    frame = pd.concat(
        [high.astype(float).rename("high"), low.astype(float).rename("low")],
        axis=1,
    )
    plus_dm = pd.Series(np.nan, index=frame.index, dtype=float, name="plus_dm")
    minus_dm = pd.Series(np.nan, index=frame.index, dtype=float, name="minus_dm")
    previous_high: float | None = None
    previous_low: float | None = None
    for index, row in frame.iterrows():
        current_high = float(row["high"])
        current_low = float(row["low"])
        valid = (
            math.isfinite(current_high)
            and math.isfinite(current_low)
            and current_high > 0
            and current_low > 0
            and current_high >= current_low
        )
        if not valid:
            previous_high = None
            previous_low = None
            continue
        if previous_high is None or previous_low is None:
            plus_dm.loc[index] = 0.0
            minus_dm.loc[index] = 0.0
        else:
            up_move = current_high - previous_high
            down_move = previous_low - current_low
            plus_dm.loc[index] = up_move if up_move > down_move and up_move > 0 else 0.0
            minus_dm.loc[index] = down_move if down_move > up_move and down_move > 0 else 0.0
        previous_high = current_high
        previous_low = current_low
    return {"plus_dm": plus_dm, "minus_dm": minus_dm}


def wilder_smoothing(values: pd.Series, period: int) -> pd.Series:
    """Lisse avec l'amorçage Wilder : SMA des ``period`` premières valeurs.

    Après l'amorçage, ``((period - 1) * précédent + courant) / period`` est
    appliqué. Le calcul redémarre après une valeur non finie, ce qui empêche une
    observation invalide de réutiliser silencieusement une ancienne valeur.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period doit être un entier supérieur ou égal à 1")
    source = values.astype(float)
    result = pd.Series(np.nan, index=source.index, dtype=float, name=source.name)
    seed: list[float] = []
    previous: float | None = None
    for index, raw_value in source.items():
        value = float(raw_value)
        if not math.isfinite(value):
            seed = []
            previous = None
            continue
        if previous is None:
            seed.append(value)
            if len(seed) < period:
                continue
            if len(seed) > period:
                seed.pop(0)
            previous = sum(seed) / period
        else:
            previous = ((period - 1) * previous + value) / period
        result.loc[index] = previous
    return result
