from pathlib import Path

path = Path("frontend/src/components/dashboard/trading-chart.test.ts")
content = path.read_text(encoding="utf-8").rstrip() + "\n"
path.write_text(content + "\n", encoding="utf-8")
