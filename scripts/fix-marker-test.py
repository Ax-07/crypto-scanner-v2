from pathlib import Path

path = Path("frontend/src/components/dashboard/trading-chart.test.ts")
content = path.read_text(encoding="utf-8")
content = content.replace(
    "function signal(time: number, indicator: MarkerIndicator, text = indicator): MarketMarker {",
    "function signal(\n  time: number,\n  indicator: MarkerIndicator,\n  text: string = indicator,\n): MarketMarker {",
)
path.write_text(content, encoding="utf-8")
