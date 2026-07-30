# Manifeste de configuration — baseline signaux/stratégie v1

## Identité

- Version : `signal-strategy-baseline-v1`
- Date de gel : 30 juillet 2026
- Commit mesuré : `770f002`
- Stratégie : `accepted_state_transition_v1`
- Contrats : observation schema 2, algorithme `signal-evaluation-v2`,
  portefeuille version 1
- Source : `backend/data/scanner_crypto.sqlite3`, ouverte en lecture seule

L'empreinte d'audit et les fingerprints par configuration sont générés dans
`signal-strategy-baseline-v1-summary.json`. Aucun golden fingerprint historique
n'est remplacé.

## Configuration canonique

```python
BacktestConfig(
    symbols=[symbol],
    start=start,
    end=end,
    signal_config=ScanConfig(timeframe=timeframe, quote="USDC"),
    horizons=[1, 3, 6, 12, 24],
    replay_mode="every_bar",
    entry_policy="next_open",
    gap_policy="reject_range",
    fee_bps=10,
    slippage_bps=0,
    snapshot_status="confirmed",
    portfolio_simulation=PortfolioSimulationConfigV1(
        version=1,
        quote_asset="USDC",
        initial_capital="10000",
        position_sizing={"mode": "percent_cash", "value": "100"},
        execution_policy="next_open",
        fee_rate="0.001",
        slippage_rate="0",
        end_of_test_policy="force_close",
    ),
)
```

Les paramètres indicateurs et confluence sont exactement les defaults
`ScanConfig` actifs : RSI 14/seuil 35, SMA/EMA 20/50, tendance 1w/1d/4h et
score minimal 2, MACD 12/26/9, Bollinger 20×2, Stochastic 14/3 et 20/80,
confluence minimale 60 avec poids 20/25/20/20/15. Aucun filtre historique ou
structuré additionnel n'est introduit.

## Sélection des marchés et timeframes

La sélection est antérieure aux performances. Ordre candidat du mode complet :

1. `BTC/USDC 4h`, actif liquide et historique profond ;
2. `BTC/USDC 1d`, profondeur longue et granularité distincte ;
3. `LINK/USDC 4h`, second actif disposant d'une plage suffisante ;
4. `ONDO/USDC 1h`, actif plus volatil et timeframe intermédiaire ;
5. `SUI/USDC 1h`, second actif plus volatil.

Pour chaque candidat, le script choisit la plus longue plage de bougies closes
strictement contiguë comptant au moins 500 points. Une combinaison absente ou
insuffisante est exclue. Les 851 combinaisons locales sont inventoriées, mais la
majorité n'a qu'environ 62 bougies 1d et 210 bougies 4h et reste non évaluable.
Toutes les données disponibles sont cotées principalement en USDC ; la diversité
de quote asset demandée n'est donc pas réalisable localement.

## Segmentation

```python
development_end = int(len(timestamps) * Decimal("0.60"))
validation_end = int(len(timestamps) * Decimal("0.80"))
development = timestamps[:development_end]
validation = timestamps[development_end:validation_end]
test_final = timestamps[validation_end:]
```

Les timestamps sont strictement croissants, sans chevauchement ni permutation.
Le test final est postérieur et gelé.

## Seuils et exclusions

- historique minimal : 500 bougies closes ;
- continuité minimale d'inventaire : 98 % ;
- exécution : plage contiguë, `gap_policy=reject_range` ;
- faible échantillon : moins de 30 trades ;
- non évaluable : aucune plage contiguë de 500 bougies ;
- aucune conclusion sur une catégorie rare.

## Matrices descriptives

```text
frais       = [0, 0.0005, 0.001, 0.002]
slippage    = [0, 0.0005, 0.001, 0.002]
sizing (%)  = [25, 50, 100]
```

La variante canonique demeure frais 0,001, slippage 0 et sizing 100. Ces
matrices ne sélectionnent aucun optimum.

## Reproduction

```powershell
cd backend
.\venv\Scripts\python.exe scripts\audit_signal_strategy_baseline.py `
  --mode full `
  --generated-at 2026-07-30T10:00:00Z
```

Le script ne fait aucun accès réseau, écrit uniquement une base de résultats
temporaire, la supprime, puis écrit le rapport Markdown et le résumé JSON compact.
Les gros détails, trades et points d'equity ne sont pas suivis.

