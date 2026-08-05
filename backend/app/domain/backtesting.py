"""Calculs purs et causaux utilisés par le rejeu historique."""

from __future__ import annotations

import math
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence, cast

import pandas as pd

from app.core.settings import OPTIONAL_INDICATOR_EXTENSION_FIELDS, ScanConfig
from app.domain.candles import Candle, candles_to_frame
from app.domain.indicator_bundle import (
    build_indicator_events,
    build_indicator_signals,
    calculate_extended_indicator_bundle,
)
from app.domain.signal_filters import (
    check_structured_signal_filters,
    include_disabled_filter_signals,
    resolve_effective_signal_filters,
)
from app.domain.indicators import (
    Availability,
    ConfluenceGrade,
    TrendState,
    calculate_bollinger_bands,
    calculate_confluence_score,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
    check_signal_filters,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_stochastic_signal,
    detect_trend,
    is_bollinger_degenerate,
)
from app.models.backtest import (
    SIGNAL_EVALUATION_VERSION,
    BacktestConfig,
    ForwardOutcome,
    SignalObservation,
)


def canonical_signal_profile_payload(config: ScanConfig) -> dict[str, Any]:
    """Sérialise le profil comme dans le contrat historique des observations."""
    excluded_profile_fields = {
        name for name in OPTIONAL_INDICATOR_EXTENSION_FIELDS if getattr(config, name, None) is None
    }
    if config.structured_signal_filters is None:
        excluded_profile_fields.add("structured_signal_filters")
    return config.model_dump(mode="json", exclude=excluded_profile_fields)


def signal_profile_fingerprint(config: ScanConfig) -> str:
    """Calcule l'identité technique canonique persistée sur les observations."""
    profile_payload = canonical_signal_profile_payload(config)
    serialized = json.dumps(profile_payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()


def _latest(series: pd.Series, digits: int = 10) -> float | None:
    valid = series.dropna()
    return round(float(valid.iloc[-1]), digits) if not valid.empty else None


def evaluate_information_set(
    *,
    job_id: str,
    symbol: str,
    decision_time_ms: int,
    primary: Sequence[Candle],
    trend_candles: Mapping[str, Sequence[Candle]],
    config: ScanConfig,
    snapshot_status: str = "confirmed",
    dataset_version: str = "unknown",
    profile_id: str = "inline",
) -> SignalObservation:
    """Évalue un signal avec uniquement les bougies closes à ``decision_time_ms``."""
    if not primary:
        raise ValueError("information set primaire vide")
    if any((item.close_time or item.open_time) > decision_time_ms for item in primary):
        raise ValueError("lookahead détecté dans l'information set primaire")
    frame = candles_to_frame(primary)
    close = float(primary[-1].close)

    rsi_series = calculate_rsi(frame["close"], config.rsi_period) if config.use_rsi else None
    valid_rsi = rsi_series.dropna() if rsi_series is not None else None
    rsi = float(valid_rsi.iloc[-1]) if valid_rsi is not None and not valid_rsi.empty else None
    rsi = round(rsi, 2) if rsi is not None else None

    primary_sma_fast: pd.Series | None = None
    primary_sma_slow: pd.Series | None = None
    primary_ema_fast: pd.Series | None = None
    primary_ema_slow: pd.Series | None = None

    if config.use_ma and config.use_sma:
        primary_sma_periods = sorted(set(config.sma_periods))

        if primary_sma_periods:
            primary_sma_fast = calculate_sma(
                frame["close"],
                primary_sma_periods[0],
            )

        if len(primary_sma_periods) >= 2:
            primary_sma_slow = calculate_sma(
                frame["close"],
                primary_sma_periods[1],
            )

    if config.use_ma and config.use_ema:
        primary_ema_periods = sorted(set(config.ema_periods))

        if primary_ema_periods:
            primary_ema_fast = calculate_ema(
                frame["close"],
                primary_ema_periods[0],
            )

        if len(primary_ema_periods) >= 2:
            primary_ema_slow = calculate_ema(
                frame["close"],
                primary_ema_periods[1],
            )

    trend_states: dict[str, TrendState] = {}
    trend_score = 0
    if config.use_ma:
        for timeframe in config.ma_timeframes:
            source = trend_candles.get(timeframe, ())
            if any((item.close_time or item.open_time) > decision_time_ms for item in source):
                raise ValueError(f"lookahead détecté sur {timeframe}")
            state: TrendState = "unavailable"
            trend_frame = candles_to_frame(source)
            if not trend_frame.empty:
                sma_values = {
                    period: _latest(calculate_sma(trend_frame["close"], period))
                    for period in config.sma_periods
                    if config.use_sma
                }
                ema_values = {
                    period: _latest(calculate_ema(trend_frame["close"], period))
                    for period in config.ema_periods
                    if config.use_ema
                }
                sma = [value for _, value in sorted(sma_values.items()) if value is not None]
                ema = [value for _, value in sorted(ema_values.items()) if value is not None]
                if sma or ema:
                    state = detect_trend(
                        trend_frame["close"],
                        sma[0] if sma else None,
                        sma[1] if len(sma) > 1 else None,
                        ema[0] if ema else None,
                        ema[1] if len(ema) > 1 else None,
                    )
            trend_states[timeframe] = state
            trend_score += int(state == "bullish")

    macd_signal: str | None = None
    macd: dict[str, pd.Series] | None = None
    if config.use_macd:
        macd = calculate_macd(
            frame["close"],
            config.macd_fast_period,
            config.macd_slow_period,
            config.macd_signal_period,
        )
        if not pd.concat(macd, axis=1).dropna().empty:
            macd_signal = detect_macd_signal(macd)

    bb_position: str | None = None
    bb_degenerate = False
    bands: dict[str, pd.Series] | None = None
    if config.use_bollinger:
        bands = calculate_bollinger_bands(
            frame["close"], config.bollinger_period, config.bollinger_std_dev
        )
        if not pd.concat(bands, axis=1).dropna().empty:
            bb_degenerate = is_bollinger_degenerate(frame["close"], bands)
            if not bb_degenerate:
                bb_position = detect_bollinger_signal(frame["close"], bands)

    stoch_signal: str | None = None
    stochastic_data: dict[str, pd.Series] | None = None
    if config.use_stochastic:
        stochastic_data = calculate_stochastic(
            frame["high"],
            frame["low"],
            frame["close"],
            config.stochastic_k_period,
            config.stochastic_d_period,
        )
        if not pd.concat(stochastic_data, axis=1).dropna().empty:
            stoch_signal = detect_stochastic_signal(
                stochastic_data, config.stochastic_oversold, config.stochastic_overbought
            )

    atr_config = config.atr
    adx_config = config.adx
    supertrend_config = config.supertrend
    donchian_config = config.donchian
    keltner_config = config.keltner
    extended_data, extended_signals = calculate_extended_indicator_bundle(
        high=frame["high"],
        low=frame["low"],
        close=frame["close"],
        use_atr=bool(atr_config and atr_config.enabled),
        atr_period=atr_config.period if atr_config else 14,
        use_adx=bool(adx_config and adx_config.enabled),
        adx_period=adx_config.period if adx_config else 14,
        adx_weak_threshold=adx_config.weak_threshold if adx_config else 20,
        adx_strong_threshold=adx_config.strong_threshold if adx_config else 25,
        use_supertrend=bool(supertrend_config and supertrend_config.enabled),
        supertrend_atr_period=supertrend_config.atr_period if supertrend_config else 10,
        supertrend_multiplier=supertrend_config.multiplier if supertrend_config else 3.0,
        use_donchian=bool(donchian_config and donchian_config.enabled),
        donchian_period=donchian_config.period if donchian_config else 20,
        use_keltner=bool(keltner_config and keltner_config.enabled),
        keltner_ema_period=keltner_config.ema_period if keltner_config else 20,
        keltner_atr_period=keltner_config.atr_period if keltner_config else 10,
        keltner_multiplier=keltner_config.multiplier if keltner_config else 2.0,
    )

    availability: dict[str, Availability] = {
        "rsi": (
            "available"
            if rsi is not None
            else "disabled" if not config.use_rsi else "insufficient_data"
        ),
        "trend": (
            "available"
            if config.use_ma and any(item != "unavailable" for item in trend_states.values())
            else "disabled" if not config.use_ma else "insufficient_data"
        ),
        "macd": (
            "available"
            if macd_signal is not None
            else "disabled" if not config.use_macd else "insufficient_data"
        ),
        "bollinger": (
            "available"
            if bb_position is not None
            else (
                "invalid_data"
                if bb_degenerate
                else "disabled" if not config.use_bollinger else "insufficient_data"
            )
        ),
        "stochastic": (
            "available"
            if stoch_signal is not None
            else "disabled" if not config.use_stochastic else "insufficient_data"
        ),
        **{name: signal["status"] for name, signal in extended_signals.items()},
    }
    active = {
        "rsi": config.use_rsi,
        "trend": config.use_ma,
        "macd": config.use_macd,
        "bollinger": config.use_bollinger,
        "stochastic": config.use_stochastic,
    }
    # Signaux structurés du timeframe principal pour RSI, SMA, EMA, MACD,
    # Bollinger, Stochastique et les indicateurs étendus.
    #
    # Les signaux SMA/EMA ci-dessous utilisent uniquement les bougies closes du
    # timeframe principal. La tendance multi-timeframes reste représentée
    # séparément par trend_states/trend_score et n'est pas fusionnée avec ces
    # signaux. Les EMA principales restent également utilisées pour produire les
    # événements ponctuels de croisement.
    indicator_signals = build_indicator_signals(
        close=frame["close"],
        rsi_series=rsi_series,
        use_rsi=config.use_rsi,
        sma_fast=primary_sma_fast,
        sma_slow=primary_sma_slow,
        use_sma=config.use_ma and config.use_sma,
        ema_fast=primary_ema_fast,
        ema_slow=primary_ema_slow,
        use_ema=config.use_ma and config.use_ema,
        macd_data=macd,
        use_macd=config.use_macd,
        bollinger_bands=bands,
        use_bollinger=config.use_bollinger,
        stochastic_data=stochastic_data,
        use_stochastic=config.use_stochastic,
        stochastic_oversold=config.stochastic_oversold,
        stochastic_overbought=config.stochastic_overbought,
        extended_signals=extended_signals,
    )
    indicator_events = build_indicator_events(
        close_series=frame["close"],
        rsi_series=rsi_series,
        ema_fast=primary_ema_fast,
        ema_slow=primary_ema_slow,
        macd_data=macd,
        bollinger_bands=bands,
        stochastic_data=stochastic_data,
        stochastic_oversold_level=config.stochastic_oversold,
        stochastic_overbought_level=config.stochastic_overbought,
        adx_weak_threshold=adx_config.weak_threshold if adx_config else 20,
        extended_data=extended_data,
        only_last=True,
    )
    confluence = (
        calculate_confluence_score(
            rsi_value=rsi,
            rsi_threshold=config.rsi_threshold,
            trend_score=trend_score,
            max_trend_score=max(1, len(config.ma_timeframes)),
            trend_states=list(trend_states.values()) if config.use_ma else None,
            macd_signal=macd_signal,
            bb_position=bb_position,
            stoch_signal=stoch_signal,
            weights={
                name: weight
                for name, weight in config.confluence_weights.items()
                if active.get(name)
            },
            availability=availability,
            raw_values={
                "rsi": rsi,
                "trend_signal": trend_states,
                "macd_signal": macd_signal,
                "bollinger_signal": bb_position,
                "stochastic_signal": stoch_signal,
            },
            indicator_signals={
                name: signal
                for name, signal in indicator_signals.items()
                if name in {"rsi", "macd", "bollinger", "stochastic"}
            },
        )
        if config.use_confluence_score
        else None
    )
    score = float(confluence["score"]) if confluence else None
    grade = cast(ConfluenceGrade | None, confluence["grade"] if confluence else None)
    factors = {
        name: cast(float | None, details.get("factor"))
        for name, details in (confluence["details"] if confluence else {}).items()
    }
    profile_payload = canonical_signal_profile_payload(config)
    profile_fingerprint = signal_profile_fingerprint(config)
    divergence_bundle: dict[str, Any] = {
        "rsi_14": rsi_series,
        "macd": macd,
    }
    from app.services.market_stream import build_divergence_markers

    divergences = build_divergence_markers(
        frame,
        divergence_bundle,
        only_newly_confirmed=True,
    )
    for divergence in divergences:
        divergence["pivot_time"] = divergence.get("time")
        divergence["confirmation_time"] = decision_time_ms // 1_000
        divergence["parameters"] = {
            "pivot_left": 3,
            "pivot_right": 3,
            "min_distance": 5,
            "max_distance": 60,
            "price_min_change": 0.001,
            "indicator_min_change": 2.0 if divergence.get("source") == "RSI" else 0.0,
        }

    filters: list[dict[str, Any]] = []

    def record(stage: str, passed: bool, reason: str | None = None) -> None:
        filters.append({"stage": stage, "passed": passed, "reason": reason})

    rsi_pass = not config.use_rsi or (rsi is not None and rsi < config.rsi_threshold)
    record("rsi", rsi_pass, None if rsi_pass else "rsi_indisponible_ou_seuil")
    trend_pass = not config.use_ma or trend_score >= config.min_trend_score
    record("trend", trend_pass, None if trend_pass else "tendance_sous_seuil")
    if config.structured_signal_filters is None:
        signal_pass = check_signal_filters(
            macd_signal=macd_signal,
            bb_position=bb_position,
            stoch_signal=stoch_signal,
            filter_macd=config.filter_macd_signal if config.use_macd else None,
            filter_bb=config.filter_bb_position if config.use_bollinger else None,
            filter_stoch=config.filter_stoch_signal if config.use_stochastic else None,
        )
    else:
        effective_filters = resolve_effective_signal_filters(
            structured_filters=config.structured_signal_filters.model_dump(mode="python"),
            filter_macd=config.filter_macd_signal if config.use_macd else None,
            filter_bb=config.filter_bb_position if config.use_bollinger else None,
            filter_stoch=config.filter_stoch_signal if config.use_stochastic else None,
        )
        signal_pass = (
            True
            if effective_filters is None
            else check_structured_signal_filters(
                indicator_signals=include_disabled_filter_signals(
                    indicator_signals=indicator_signals,
                    disabled_indicators=[
                        name
                        for name, enabled in (
                            ("macd", config.use_macd),
                            ("bollinger", config.use_bollinger),
                            ("stochastic", config.use_stochastic),
                        )
                        if not enabled
                    ],
                ),
                filters=effective_filters,
            )
        )
    record("signal_filters", signal_pass, None if signal_pass else "classe_non_autorisee")
    confluence_pass = not config.use_confluence_score or (
        score is not None and score >= config.min_confluence_score
    )
    record(
        "confluence",
        confluence_pass,
        None if confluence_pass else "confluence_indisponible_ou_sous_seuil",
    )
    first_failure = next((item for item in filters if not item["passed"]), None)
    accepted = first_failure is None
    return SignalObservation(
        job_id=job_id,
        symbol=symbol,
        timeframe=config.timeframe,
        decision_time=datetime.fromtimestamp(decision_time_ms / 1_000, tz=timezone.utc),
        created_at=datetime.fromtimestamp(decision_time_ms / 1_000, tz=timezone.utc),
        snapshot_status=cast(Any, snapshot_status),
        accepted=accepted,
        rejection_stage=first_failure["stage"] if first_failure else None,
        rejection_reason=first_failure["reason"] if first_failure else None,
        close=close,
        rsi=rsi,
        trend_score=trend_score if config.use_ma else None,
        trend_states=trend_states,
        macd_signal=macd_signal,
        bollinger_position=bb_position,
        stochastic_signal=stoch_signal,
        confluence_score=score,
        confluence_grade=grade,
        confluence_factors=factors,
        availability=availability,
        indicator_signals=cast(Any, indicator_signals),
        indicator_events=cast(Any, indicator_events),
        filter_trace=filters,
        algorithm_version=SIGNAL_EVALUATION_VERSION,
        profile_id=profile_id,
        profile_fingerprint=profile_fingerprint,
        dataset_version=dataset_version,
        source_open_time=datetime.fromtimestamp(primary[-1].open_time / 1_000, tz=timezone.utc),
        source_ohlcv={
            "open": primary[-1].open,
            "high": primary[-1].high,
            "low": primary[-1].low,
            "close": primary[-1].close,
            "volume": primary[-1].volume,
        },
        raw_values={
            "rsi": rsi,
            "trend": trend_states,
            "macd": macd_signal,
            "bollinger": bb_position,
            "stochastic": stoch_signal,
        },
        classes={
            "macd": macd_signal,
            "bollinger": bb_position,
            "stochastic": stoch_signal,
        },
        trend_net_score=(
            sum(
                1 if state == "bullish" else -1 if state == "bearish" else 0
                for state in trend_states.values()
            )
            if config.use_ma
            else None
        ),
        confluence_breakdown=confluence["breakdown"] if confluence else {},
        configured_weights={
            name: float(weight)
            for name, weight in config.confluence_weights.items()
            if active.get(name)
        },
        effective_weights=confluence["effective_weights"] if confluence else {},
        signal_profile=profile_payload,
        divergences=divergences,
        quality={
            "available_bars": len(primary),
            "zero_volume_ratio": sum(item.volume == 0 for item in primary) / len(primary),
            "constant_candle_ratio": sum(
                item.open == item.high == item.low == item.close for item in primary
            )
            / len(primary),
            "quote_volume_median": statistics.median(item.close * item.volume for item in primary),
        },
    )


def calculate_forward_outcomes(
    observation_id: int | None,
    candles: Sequence[Candle],
    decision_index: int,
    config: BacktestConfig,
    *,
    blocked_intervals: set[int] | None = None,
) -> list[ForwardOutcome]:
    """Mesure les rendements forward; les fenêtres incomplètes sont censurées."""
    blocked = blocked_intervals or set()
    entry_index = decision_index if config.entry_policy == "signal_close" else decision_index + 1
    outcomes: list[ForwardOutcome] = []
    for horizon in config.horizons:
        exit_index = entry_index + horizon
        if entry_index >= len(candles) or exit_index >= len(candles):
            outcomes.append(
                ForwardOutcome(
                    observation_id=observation_id,
                    horizon=horizon,
                    entry_policy=config.entry_policy,
                    censored=True,
                    censor_reason="fin_de_serie",
                    available_bars=max(0, len(candles) - entry_index),
                    valid=False,
                )
            )
            continue
        if any(index in blocked for index in range(entry_index, exit_index + 1)):
            outcomes.append(
                ForwardOutcome(
                    observation_id=observation_id,
                    horizon=horizon,
                    entry_policy=config.entry_policy,
                    censored=True,
                    censor_reason="trou_de_donnees",
                    available_bars=max(0, min(len(candles), exit_index + 1) - entry_index),
                    valid=False,
                )
            )
            continue
        entry = (
            candles[decision_index].close
            if config.entry_policy == "signal_close"
            else candles[entry_index].open
        )
        exit_price = candles[exit_index].close
        path = candles[entry_index : exit_index + 1]
        gross = exit_price / entry - 1
        friction = config.slippage_bps / 10_000
        fee = config.fee_bps / 10_000
        effective_entry = entry * (1 + friction) * (1 + fee)
        effective_exit = exit_price * (1 - friction) * (1 - fee)
        outcomes.append(
            ForwardOutcome(
                observation_id=observation_id,
                horizon=horizon,
                entry_policy=config.entry_policy,
                entry_time=datetime.fromtimestamp(
                    (
                        candles[entry_index].open_time
                        if config.entry_policy == "next_open"
                        else (
                            candles[decision_index].close_time or candles[decision_index].open_time
                        )
                    )
                    / 1_000,
                    tz=timezone.utc,
                ),
                entry_price=entry,
                exit_time=datetime.fromtimestamp(
                    (candles[exit_index].close_time or candles[exit_index].open_time) / 1_000,
                    tz=timezone.utc,
                ),
                exit_price=exit_price,
                gross_return=round(gross, 10),
                net_return=round(effective_exit / effective_entry - 1, 10),
                mfe=round(max(item.high for item in path) / entry - 1, 10),
                mae=round(min(item.low for item in path) / entry - 1, 10),
                highest_price=max(item.high for item in path),
                lowest_price=min(item.low for item in path),
                available_bars=len(path),
            )
        )
    return outcomes


def descriptive(values: Iterable[float]) -> dict[str, Any]:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return {"count": 0}

    def quantile(p: float) -> float:
        position = (len(clean) - 1) * p
        low = math.floor(position)
        high = math.ceil(position)
        return (
            clean[low]
            if low == high
            else clean[low] + (clean[high] - clean[low]) * (position - low)
        )

    return {
        "count": len(clean),
        "mean": statistics.fmean(clean),
        "median": statistics.median(clean),
        "std": statistics.pstdev(clean),
        "min": clean[0],
        "q05": quantile(0.05),
        "q25": quantile(0.25),
        "q75": quantile(0.75),
        "q95": quantile(0.95),
        "max": clean[-1],
        "positive_rate": sum(value > 0 for value in clean) / len(clean),
        "negative_rate": sum(value < 0 for value in clean) / len(clean),
        "zero_rate": sum(value == 0 for value in clean) / len(clean),
    }


def outcome_statistics(items: Sequence[ForwardOutcome]) -> dict[str, Any]:
    valid = [item for item in items if not item.censored and item.net_return is not None]
    result = descriptive(cast(list[float], [item.net_return for item in valid]))
    result.update(
        {
            "gross": descriptive(
                cast(
                    list[float],
                    [item.gross_return for item in valid if item.gross_return is not None],
                )
            ),
            "net": descriptive(
                cast(
                    list[float], [item.net_return for item in valid if item.net_return is not None]
                )
            ),
            "mfe": descriptive(
                cast(list[float], [item.mfe for item in valid if item.mfe is not None])
            ),
            "mae": descriptive(
                cast(list[float], [item.mae for item in valid if item.mae is not None])
            ),
            "censored_count": sum(item.censored for item in items),
            "coverage": len(valid) / len(items) if items else 0,
        }
    )
    mfe_median = result["mfe"].get("median")
    mae_median = result["mae"].get("median")
    result["mfe_abs_mae_ratio"] = (
        mfe_median / abs(mae_median)
        if isinstance(mfe_median, (int, float))
        and isinstance(mae_median, (int, float))
        and mae_median
        else None
    )
    return result


def build_analytics(
    observations: Sequence[SignalObservation],
    outcomes: Sequence[ForwardOutcome],
    config: BacktestConfig,
    warnings: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Construit résumé, corrélations pairwise, cooccurrences et ablations."""
    by_observation = {item.id: item for item in observations}
    horizon_items: dict[int, list[ForwardOutcome]] = defaultdict(list)
    censored = 0
    for outcome in outcomes:
        if outcome.censored:
            censored += 1
        horizon_items[outcome.horizon].append(outcome)

    funnel = []
    remaining = list(observations)
    for stage in ("rsi", "trend", "signal_filters", "confluence"):
        before = len(remaining)
        before_ids = {item.id for item in remaining}
        before_returns = [
            item.net_return
            for item in outcomes
            if item.observation_id in before_ids
            and item.net_return is not None
            and not item.censored
        ]
        remaining = [
            item
            for item in remaining
            if next(
                (trace["passed"] for trace in item.filter_trace if trace["stage"] == stage),
                True,
            )
        ]
        after_ids = {item.id for item in remaining}
        after_returns = [
            item.net_return
            for item in outcomes
            if item.observation_id in after_ids
            and item.net_return is not None
            and not item.censored
        ]
        rejected_ids = before_ids - after_ids
        rejected_returns = [
            item.net_return
            for item in outcomes
            if item.observation_id in rejected_ids
            and item.net_return is not None
            and not item.censored
        ]
        unavailable = sum(
            any(value != "available" for value in item.availability.values())
            for item in observations
            if item.id in before_ids
        )
        funnel.append(
            {
                "stage": stage,
                "input": before,
                "passed": len(remaining),
                "rejected": before - len(remaining),
                "unavailable": unavailable,
                "outcomes_before": descriptive(cast(list[float], before_returns)),
                "outcomes_after": descriptive(cast(list[float], after_returns)),
                "outcomes_rejected": descriptive(cast(list[float], rejected_returns)),
            }
        )

    segments: dict[str, dict[str, Any]] = {}
    for attribute in ("confluence_grade", "macd_signal", "bollinger_position", "stochastic_signal"):
        category_groups: dict[str, list[float]] = defaultdict(list)
        for outcome in outcomes:
            observation = by_observation.get(outcome.observation_id)
            value = getattr(observation, attribute, None) if observation else None
            if value is not None and outcome.net_return is not None and not outcome.censored:
                category_groups[str(value)].append(outcome.net_return)
        segments[attribute] = {
            name: descriptive(values) for name, values in category_groups.items()
        }
    trend_groups: dict[str, list[float]] = defaultdict(list)
    for outcome in outcomes:
        observation = by_observation.get(outcome.observation_id)
        if observation and outcome.net_return is not None and not outcome.censored:
            state = ",".join(sorted(set(observation.trend_states.values()))) or "none"
            trend_groups[state].append(outcome.net_return)
    segments["trend_state"] = {name: descriptive(values) for name, values in trend_groups.items()}
    rsi_groups: dict[str, list[float]] = defaultdict(list)
    score_groups: dict[str, list[float]] = defaultdict(list)
    for outcome in outcomes:
        observation = by_observation.get(outcome.observation_id)
        if observation is None or outcome.net_return is None or outcome.censored:
            continue
        if observation.rsi is not None:
            rsi_zone = (
                "oversold"
                if observation.rsi < 30
                else (
                    "low"
                    if observation.rsi < 50
                    else "high" if observation.rsi < 70 else "overbought"
                )
            )
            rsi_groups[rsi_zone].append(outcome.net_return)
        if observation.confluence_score is not None:
            lower = int(observation.confluence_score // 10 * 10)
            score_groups[f"{lower:02d}-{min(100, lower + 9):02d}"].append(outcome.net_return)
    segments["rsi_zone"] = {name: descriptive(values) for name, values in rsi_groups.items()}
    segments["confluence_score_band"] = {
        name: descriptive(values) for name, values in score_groups.items()
    }
    for segment_name, getter in {
        "symbol": lambda item: item.symbol,
        "timeframe": lambda item: item.timeframe,
        "year": lambda item: str(item.decision_time.year),
        "month": lambda item: item.decision_time.strftime("%Y-%m"),
        "available_factor_count": lambda item: str(
            sum(value == "available" for value in item.availability.values())
        ),
        "accepted": lambda item: str(item.accepted).lower(),
    }.items():
        segment_groups: dict[str, list[float]] = defaultdict(list)
        for outcome in outcomes:
            observation = by_observation.get(outcome.observation_id)
            if observation and outcome.net_return is not None and not outcome.censored:
                segment_groups[getter(observation)].append(outcome.net_return)
        segments[segment_name] = {
            name: descriptive(values) for name, values in segment_groups.items()
        }
    for factor in sorted({name for item in observations for name in item.availability}):
        availability_groups: dict[str, list[float]] = defaultdict(list)
        for outcome in outcomes:
            observation = by_observation.get(outcome.observation_id)
            if observation and outcome.net_return is not None and not outcome.censored:
                availability_groups[str(observation.availability.get(factor, "missing"))].append(
                    outcome.net_return
                )
        segments[f"availability:{factor}"] = {
            name: descriptive(values) for name, values in availability_groups.items()
        }

    summary = {
        "observation_count": len(observations),
        "accepted_count": sum(item.accepted for item in observations),
        "rejected_count": sum(not item.accepted for item in observations),
        "censored_count": censored,
        "warnings": warnings,
        "horizons": {
            str(key): outcome_statistics(values) for key, values in sorted(horizon_items.items())
        },
        "segments": segments,
        "filter_funnel": funnel,
        "provisional_supported": False,
        "trade_simulation_included": False,
    }

    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        observation = by_observation.get(outcome.observation_id)
        if observation is None or outcome.net_return is None or outcome.censored:
            continue
        row = {
            "horizon": outcome.horizon,
            "outcome": outcome.net_return,
            "rsi": observation.rsi,
            "trend": observation.trend_score,
            "confluence": observation.confluence_score,
            **{f"factor_{name}": value for name, value in observation.confluence_factors.items()},
        }
        rows.append(row)
    correlations: dict[str, Any] = {"by_horizon": {}, "availability": {}, "cooccurrence": {}}
    frame = pd.DataFrame(rows)
    if not frame.empty:
        for horizon, group in frame.groupby("horizon"):
            numeric = group.drop(columns=["horizon"])
            pearson = numeric.corr(method="pearson", min_periods=2)
            spearman = numeric.corr(method="spearman", min_periods=2)
            correlations["by_horizon"][str(horizon)] = {
                "pearson": pearson.astype(object).where(pd.notna(pearson), None).to_dict(),
                "spearman": spearman.astype(object).where(pd.notna(spearman), None).to_dict(),
                "pair_counts": {
                    left: {
                        right: int(numeric[[left, right]].dropna().shape[0])
                        for right in numeric.columns
                    }
                    for left in numeric.columns
                },
            }
    factor_names = sorted({name for item in observations for name in item.availability})
    correlations["availability"] = {
        name: dict(Counter(str(item.availability.get(name, "missing")) for item in observations))
        for name in factor_names
    }
    for left in factor_names:
        correlations["cooccurrence"][left] = {
            right: sum(
                item.availability.get(left) == "available"
                and item.availability.get(right) == "available"
                for item in observations
            )
            for right in factor_names
        }

    ablations: dict[str, Any] = {}
    weights = config.signal_config.confluence_weights
    threshold = config.signal_config.min_confluence_score
    removal_sets: dict[str, set[str]] = {name: {name} for name in factor_names} | {
        "group:momentum": {"rsi", "stochastic"},
        "group:trend": {"trend"},
        "group:confirmation": {"macd", "bollinger"},
    }
    for label, removed in removal_sets.items():
        accepted_ids: set[int | None] = set()
        for observation in observations:
            other_filters_pass = all(
                trace["passed"]
                for trace in observation.filter_trace
                if trace["stage"] != "confluence"
            )
            if not other_filters_pass:
                continue
            factors = {
                name: value
                for name, value in observation.confluence_factors.items()
                if name not in removed and value is not None and weights.get(name, 0) > 0
            }
            total = sum(weights[name] for name in factors)
            score = (
                sum(cast(float, factors[name]) * weights[name] for name in factors) / total * 100
                if total
                else None
            )
            if score is not None and score >= threshold:
                accepted_ids.add(observation.id)
        by_horizon = {
            str(horizon): descriptive(
                cast(
                    list[float],
                    [
                        item.net_return
                        for item in outcomes
                        if item.observation_id in accepted_ids
                        and item.horizon == horizon
                        and item.net_return is not None
                        and not item.censored
                    ],
                )
            )
            for horizon in config.horizons
        }
        ablations[label] = {
            "removed_factors": sorted(removed),
            "accepted_count": len(accepted_ids),
            "delta_vs_baseline": len(accepted_ids) - sum(item.accepted for item in observations),
            "horizons": by_horizon,
        }
    return summary, correlations, ablations
