"""Adaptateurs purs entre replay public et moteur de portefeuille."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from app.core.settings import OPTIONAL_INDICATOR_EXTENSION_FIELDS
from app.domain.candles import Candle, timeframe_milliseconds, timestamp_ms_to_utc
from app.domain.portfolio import (
    EndOfTestPolicy,
    ExecutionPolicy,
    PortfolioSimulationConfig,
    PortfolioSimulationResult,
    PortfolioSimulationStep,
    PositionSizingMode,
)
from app.models.backtest import BacktestConfig, SignalObservation
from app.models.portfolio import (
    PortfolioSimulationConfigV1,
    PortfolioSimulationPublicResult,
    PortfolioSimulationSummary,
)


class PortfolioReplayError(ValueError):
    """Erreur causale stable et présentable sans stack trace au client."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def to_internal_portfolio_config(
    public_config: PortfolioSimulationConfigV1,
) -> PortfolioSimulationConfig:
    """Convertit sans défaut caché le contrat public vers le domaine pur."""
    return PortfolioSimulationConfig(
        version=public_config.version,
        quote_asset=public_config.quote_asset,
        initial_capital=public_config.initial_capital,
        position_sizing_mode=PositionSizingMode(public_config.position_sizing.mode),
        position_size_percent=public_config.position_sizing.value,
        execution_policy=ExecutionPolicy(public_config.execution_policy),
        fee_rate=public_config.fee_rate,
        slippage_rate=public_config.slippage_rate,
        end_of_test_policy=EndOfTestPolicy(public_config.end_of_test_policy),
    )


def _aware_utc(value: datetime | None, *, code: str, name: str) -> datetime:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        raise PortfolioReplayError(code, f"{name} doit inclure un fuseau horaire")
    return value.astimezone(timezone.utc)


def build_portfolio_simulation_steps(
    *,
    observations: Sequence[SignalObservation],
    primary_candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
) -> tuple[PortfolioSimulationStep, ...]:
    """Relie exactement chaque observation conservée à sa bougie primaire."""
    if not observations:
        raise PortfolioReplayError(
            "portfolio_missing_observation",
            "la simulation exige au moins une observation causale",
        )
    try:
        interval_ms = timeframe_milliseconds(timeframe)
    except ValueError as exc:
        raise PortfolioReplayError("portfolio_invalid_timeframe", str(exc)) from exc

    candles_by_open: dict[datetime, Candle] = {}
    for candle in primary_candles:
        if candle.symbol != symbol:
            raise PortfolioReplayError(
                "portfolio_symbol_mismatch",
                f"bougie {candle.symbol!r} incompatible avec {symbol!r}",
            )
        if candle.timeframe != timeframe:
            raise PortfolioReplayError(
                "portfolio_timeframe_mismatch",
                f"bougie {candle.timeframe!r} incompatible avec {timeframe!r}",
            )
        opened = timestamp_ms_to_utc(candle.open_time)
        if opened in candles_by_open:
            raise PortfolioReplayError(
                "portfolio_duplicate_primary_candle",
                f"plusieurs bougies ouvrent à {opened.isoformat()}",
            )
        candles_by_open[opened] = candle

    steps: list[PortfolioSimulationStep] = []
    observation_ids: set[int] = set()
    previous_open = None
    previous_decision = None
    for observation in observations:
        if observation.id is None:
            raise PortfolioReplayError(
                "portfolio_missing_observation_id",
                "une observation persistée ne possède pas d'identifiant",
            )
        if observation.id in observation_ids:
            raise PortfolioReplayError(
                "portfolio_duplicate_observation",
                f"observation dupliquée: {observation.id}",
            )
        observation_ids.add(observation.id)
        if observation.symbol != symbol:
            raise PortfolioReplayError(
                "portfolio_symbol_mismatch",
                f"observation {observation.symbol!r} incompatible avec {symbol!r}",
            )
        if observation.timeframe != timeframe:
            raise PortfolioReplayError(
                "portfolio_timeframe_mismatch",
                f"observation {observation.timeframe!r} incompatible avec {timeframe!r}",
            )
        source_open = _aware_utc(
            observation.source_open_time,
            code="portfolio_invalid_timestamp",
            name="source_open_time",
        )
        decision = _aware_utc(
            observation.decision_time,
            code="portfolio_invalid_timestamp",
            name="decision_time",
        )
        matched_candle = candles_by_open.get(source_open)
        if matched_candle is None:
            raise PortfolioReplayError(
                "portfolio_missing_primary_candle",
                f"aucune bougie primaire à {source_open.isoformat()}",
            )
        expected_decision = timestamp_ms_to_utc(
            matched_candle.close_time
            if matched_candle.close_time is not None
            else matched_candle.open_time + interval_ms
        )
        if decision != expected_decision:
            raise PortfolioReplayError(
                "portfolio_incoherent_decision_time",
                f"décision {decision.isoformat()} différente de {expected_decision.isoformat()}",
            )
        if previous_open is not None and previous_decision is not None:
            if source_open <= previous_open or decision <= previous_decision:
                raise PortfolioReplayError(
                    "portfolio_invalid_step_order",
                    "les observations doivent être strictement ordonnées",
                )
            actual_ms = int((source_open - previous_open).total_seconds() * 1_000)
            if actual_ms != interval_ms:
                raise PortfolioReplayError(
                    "portfolio_time_gap",
                    f"intervalle primaire attendu {interval_ms} ms, obtenu {actual_ms} ms",
                )
        try:
            step = PortfolioSimulationStep(
                observation_id=str(observation.id),
                source_open_time=source_open,
                decision_time=decision,
                open_price=Decimal(str(matched_candle.open)),
                close_price=Decimal(str(matched_candle.close)),
                accepted=observation.accepted,
            )
        except ValueError as exc:
            raise PortfolioReplayError("portfolio_invalid_price", str(exc)) from exc
        steps.append(step)
        previous_open = source_open
        previous_decision = decision
    return tuple(steps)


def to_public_portfolio_summary(
    result: PortfolioSimulationResult,
) -> PortfolioSimulationSummary:
    """Projette directement les métriques internes, sans les recalculer."""
    metrics = result.metrics
    return PortfolioSimulationSummary(
        version=result.version,
        quote_asset=result.quote_asset,
        initial_capital=metrics.initial_capital,
        final_cash=metrics.final_cash,
        final_equity=metrics.final_equity,
        net_profit=metrics.net_profit,
        total_return_ratio=metrics.total_return_ratio,
        realized_pnl=metrics.realized_pnl,
        unrealized_pnl=metrics.unrealized_pnl,
        total_fees=metrics.total_fees,
        trade_count=metrics.trade_count,
        winning_trade_count=metrics.winning_trade_count,
        losing_trade_count=metrics.losing_trade_count,
        breakeven_trade_count=metrics.breakeven_trade_count,
        win_rate=metrics.win_rate,
        average_trade_return=metrics.average_trade_return,
        max_drawdown_ratio=metrics.max_drawdown_ratio,
        exposure_ratio=metrics.exposure_ratio,
        open_position_count=metrics.open_position_count,
    )


def to_public_portfolio_result(
    result: PortfolioSimulationResult,
) -> PortfolioSimulationPublicResult:
    """Construit l'aperçu public borné du résultat interne."""
    return PortfolioSimulationPublicResult(
        version=result.version,
        quote_asset=result.quote_asset,
        summary=to_public_portfolio_summary(result),
        has_trades=bool(result.trades),
        has_equity_curve=bool(result.equity_curve),
    )


def backtest_config_fingerprint(config: BacktestConfig) -> str:
    """Étend exactement le fingerprint historique seulement si nécessaire."""
    optional_fields = OPTIONAL_INDICATOR_EXTENSION_FIELDS | {"structured_signal_filters"}
    excluded_fields = {
        field for field in optional_fields if getattr(config.signal_config, field) is None
    }
    profile_payload = config.signal_config.model_dump(
        mode="json",
        exclude=excluded_fields or None,
    )
    if config.portfolio_simulation is not None:
        profile_payload["portfolio_simulation"] = config.portfolio_simulation.model_dump(
            mode="json"
        )
    encoded = json.dumps(
        profile_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
