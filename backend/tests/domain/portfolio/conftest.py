from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.portfolio import PortfolioSimulationStep


def make_steps(
    accepted: list[bool],
    *,
    opens: list[str] | None = None,
    closes: list[str] | None = None,
) -> list[PortfolioSimulationStep]:
    """Construit une petite série horaire déterministe."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    open_values = opens or ["100"] * len(accepted)
    close_values = closes or open_values
    return [
        PortfolioSimulationStep(
            observation_id=f"observation-{index + 1:06d}",
            source_open_time=start + timedelta(hours=index),
            decision_time=start + timedelta(hours=index + 1),
            open_price=Decimal(open_values[index]),
            close_price=Decimal(close_values[index]),
            accepted=value,
        )
        for index, value in enumerate(accepted)
    ]
