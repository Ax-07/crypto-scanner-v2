"""Builder commun pour construire les signaux structurés (``IndicatorSignal``).

Ce module factorise, en un seul endroit, la construction des ``IndicatorSignal``
consommés par :func:`app.domain.indicators.confluence.calculate_confluence_score`
en mode structuré. Il est utilisé par le moteur canonique
(:mod:`app.domain.backtesting`, partagé par le scanner et le backtest) et par
:mod:`app.services.market_stream`, afin d'éviter toute duplication de la
logique de construction entre ces services.

Décisions de conception:

- Le statut ``"disabled"`` n'est renvoyé que lorsque le flag ``use_*``
  correspondant est ``False`` — jamais pour un historique insuffisant ou une
  donnée invalide, ce qui reste du ressort des fonctions ``detect_*_signal``/
  ``build_*_signal`` de chaque indicateur.
- Les clés ``sma``/``ema`` ne sont ajoutées que si les séries rapides
  correspondantes sont fournies: le scanner et le backtest, qui gèrent une
  tendance multi-timeframes distincte via ``trend_states``/``trend_score``,
  n'utilisent délibérément pas ce builder pour la tendance et n'appellent
  cette fonction qu'avec ``use_sma=False``/``use_ema=False`` (valeurs par
  défaut). Seul :mod:`app.services.market_stream` (tendance sur un seul
  timeframe) fournit ces séries.
- Stochastique: lorsque l'historique disponible ne compte qu'une seule ligne
  valide (``%K``/``%D`` définis simultanément une seule fois), la fonction
  historique :func:`app.domain.indicators.stochastic.detect_stochastic_signal`
  renvoie inconditionnellement ``"neutral"`` (elle exige au moins deux points
  pour toute autre classification), alors que
  :func:`app.domain.indicators.stochastic.build_stochastic_signal` classerait
  cette ligne unique selon la zone réelle de ``%K``/``%D``. Pour préserver une
  parité stricte avec le mode historique dans ce cas limite, ce builder force
  alors un statut ``"insufficient_data"`` (l'indicateur ne participe pas au
  score structuré ce tour-ci, comme un historique vraiment insuffisant). En
  pratique, ce cas ne se produit qu'à l'amorçage et disparaît dès que
  ``min_ohlcv_bars`` (toujours trop grand pour laisser un tel cas isolé
  subsister) est respecté.
"""

from __future__ import annotations

import pandas as pd

from app.domain.indicators.bollinger import build_bollinger_signal
from app.domain.indicators.macd import build_macd_signal
from app.domain.indicators.moving_averages import detect_moving_average_signal
from app.domain.indicators.rsi import detect_rsi_signal
from app.domain.indicators.stochastic import build_stochastic_signal
from app.domain.indicators.types import IndicatorSignal, _unavailable_signal

__all__ = ["build_indicator_signals"]


def build_indicator_signals(
    *,
    close: pd.Series,
    rsi_series: pd.Series | float | None = None,
    use_rsi: bool = True,
    sma_fast: pd.Series | None = None,
    sma_slow: pd.Series | None = None,
    use_sma: bool = False,
    ema_fast: pd.Series | None = None,
    ema_slow: pd.Series | None = None,
    use_ema: bool = False,
    macd_data: dict[str, pd.Series] | None = None,
    use_macd: bool = True,
    bollinger_bands: dict[str, pd.Series] | None = None,
    use_bollinger: bool = True,
    stochastic_data: dict[str, pd.Series] | None = None,
    use_stochastic: bool = True,
    stochastic_oversold: float = 20,
    stochastic_overbought: float = 80,
) -> dict[str, IndicatorSignal]:
    """Construit les ``IndicatorSignal`` disponibles à partir des séries calculées.

    Chaque section n'est incluse dans le résultat que si son flag ``use_*``
    est vrai; ``sma``/``ema`` exigent en plus une série rapide non ``None``.
    Les séries doivent déjà être calculées par l'appelant (ce module ne fait
    aucun calcul d'indicateur, seulement la construction du signal structuré).
    """
    signals: dict[str, IndicatorSignal] = {}

    if use_rsi:
        signals["rsi"] = detect_rsi_signal(rsi_series)

    if use_sma and sma_fast is not None:
        signals["sma"] = detect_moving_average_signal(close, sma_fast, sma_slow, family="sma")

    if use_ema and ema_fast is not None:
        signals["ema"] = detect_moving_average_signal(close, ema_fast, ema_slow, family="ema")

    if use_macd:
        signals["macd"] = (
            build_macd_signal(macd_data)
            if macd_data is not None
            else _unavailable_signal("insufficient_data", "Historique de MACD insuffisant")
        )

    if use_bollinger:
        signals["bollinger"] = (
            build_bollinger_signal(close, bollinger_bands)
            if bollinger_bands is not None
            else _unavailable_signal("insufficient_data", "Historique de Bollinger insuffisant")
        )

    if use_stochastic:
        if stochastic_data is None:
            signals["stochastic"] = _unavailable_signal(
                "insufficient_data", "Historique de stochastique insuffisant"
            )
        else:
            valid_rows = pd.concat(
                [stochastic_data["k"].rename("k"), stochastic_data["d"].rename("d")], axis=1
            ).dropna()
            if len(valid_rows) < 2:
                signals["stochastic"] = _unavailable_signal(
                    "insufficient_data", "Historique de stochastique insuffisant"
                )
            else:
                signals["stochastic"] = build_stochastic_signal(
                    stochastic_data, stochastic_oversold, stochastic_overbought
                )

    return signals
