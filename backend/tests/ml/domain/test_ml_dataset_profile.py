from app.core.settings import (
    OPTIONAL_INDICATOR_EXTENSION_FIELDS,
    ScanConfig,
)
from app.ml.domain.ml_dataset_profile import (
    ML_DATASET_PROFILE_V2_ID,
    build_ml_dataset_profile_v2,
)


def test_ml_dataset_profile_v2_has_stable_identifier() -> None:
    assert ML_DATASET_PROFILE_V2_ID == "ml-dataset-v2"


def test_ml_dataset_profile_v2_preserves_historical_defaults() -> None:
    baseline = ScanConfig(
        timeframe="1h",
        quote="USDC",
    )
    profile = build_ml_dataset_profile_v2(
        timeframe="1h",
        quote="USDC",
    )

    excluded_extensions = set(OPTIONAL_INDICATOR_EXTENSION_FIELDS)

    assert profile.model_dump(
        exclude=excluded_extensions,
    ) == baseline.model_dump(
        exclude=excluded_extensions,
    )


def test_ml_dataset_profile_v2_enables_all_extensions() -> None:
    profile = build_ml_dataset_profile_v2(
        timeframe="1h",
    )

    assert profile.atr is not None
    assert profile.atr.enabled
    assert profile.atr.period == 14

    assert profile.adx is not None
    assert profile.adx.enabled
    assert profile.adx.period == 14
    assert profile.adx.weak_threshold == 20
    assert profile.adx.strong_threshold == 25

    assert profile.supertrend is not None
    assert profile.supertrend.enabled
    assert profile.supertrend.atr_period == 10
    assert profile.supertrend.multiplier == 3.0

    assert profile.donchian is not None
    assert profile.donchian.enabled
    assert profile.donchian.period == 20

    assert profile.keltner is not None
    assert profile.keltner.enabled
    assert profile.keltner.ema_period == 20
    assert profile.keltner.atr_period == 10
    assert profile.keltner.multiplier == 2.0


def test_ml_dataset_profile_v2_keeps_historical_confluence() -> None:
    profile = build_ml_dataset_profile_v2(
        timeframe="1h",
    )

    assert profile.confluence_weights == {
        "rsi": 20.0,
        "trend": 25.0,
        "macd": 20.0,
        "bollinger": 20.0,
        "stochastic": 15.0,
    }

    assert not (OPTIONAL_INDICATOR_EXTENSION_FIELDS & set(profile.confluence_weights))


def test_ml_dataset_profile_v2_is_deterministic_and_normalizes_quote() -> None:
    first = build_ml_dataset_profile_v2(
        timeframe="1h",
        quote=" usdc ",
    )
    second = build_ml_dataset_profile_v2(
        timeframe="1h",
        quote="USDC",
    )

    assert first.quote == "USDC"
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
