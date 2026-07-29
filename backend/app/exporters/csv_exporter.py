"""Sérialise les résultats publics de scan dans un CSV déterministe."""

from __future__ import annotations

import csv
import io
import json

from app.models.scanner import ScanResult

CSV_COLUMNS = [
    "symbol",
    "timeframe",
    "rsi",
    "last_close_price",
    "last_close_time",
    "trend_score",
    "trends",
    "moving_averages",
    "macd",
    "macd_signal",
    "macd_histogram",
    "macd_signal_type",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_position",
    "stoch_k",
    "stoch_d",
    "stoch_signal",
    "confluence_score",
    "confluence_grade",
    "confluence_breakdown",
    "confluence_effective_weights",
]
# NB: `ScanResult.indicator_signals` (signaux structures IndicatorSignal par
# indicateur) n'est volontairement PAS exporte en colonne CSV pour cette
# phase: c'est un dict de dicts imbrique (un IndicatorSignal complet par
# indicateur), dont l'aplatissement en CSV lisible/reimportable demanderait
# soit une colonne JSON par indicateur soit un prefixage de colonnes
# (ex. rsi_status, rsi_direction, ...), ce qui alourdirait significativement
# le format sans consommateur identifie a ce jour. Les champs legacy
# (rsi, macd, bb_*, stoch_*, ...) restent la source exportee. A revisiter si
# un besoin d'export structure emerge.


def results_to_csv(results: list[ScanResult]) -> str:
    """Convertit des résultats en CSV avec en-tête, même si la liste est vide.

    Les dictionnaires imbriqués sont encodés comme objets JSON afin de rester
    lisibles et réimportables depuis une cellule CSV.
    """
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for item in results:
        row = item.model_dump(mode="json")
        for key in (
            "trends",
            "moving_averages",
            "confluence_breakdown",
            "confluence_effective_weights",
        ):
            row[key] = json.dumps(row.get(key, {}), ensure_ascii=False)
        writer.writerow({column: row.get(column) for column in CSV_COLUMNS})
    return stream.getvalue()
