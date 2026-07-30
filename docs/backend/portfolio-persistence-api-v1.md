# Persistance et API du portefeuille v1 — Phase 6.4

## Périmètre et compatibilité

La Phase 6.4 persiste les détails produits par le moteur de portefeuille v1 et
les expose par pagination et exports CSV. Elle ne change aucune formule du
moteur, aucun outcome historique, checkpoint ou fingerprint, ni le frontend.

```text
portfolio_simulation absent
→ aucun appel au moteur de portefeuille
→ aucun détail écrit
→ payloads, outcomes et exports historiques inchangés
```

## Architecture et schéma

`PortfolioRepository` utilise le même `Database`, les mêmes connexions
`aiosqlite` et les mêmes réglages que les autres repositories : foreign keys,
`synchronous=NORMAL`, `busy_timeout=5000` et WAL. Il ne dépend pas de FastAPI.

La migration applicative 8 ajoute un schéma de détail de version 1 :

| Table | Rôle | Clé principale |
|---|---|---|
| `backtest_portfolio_runs` | métadonnées, configuration, métriques, état final | `job_id` |
| `backtest_portfolio_orders` | ordres dans l'ordre du moteur | `(job_id, sequence)` |
| `backtest_portfolio_executions` | exécutions exactes | `(job_id, sequence)` |
| `backtest_portfolio_trades` | trades fermés exacts | `(job_id, sequence)` |
| `backtest_portfolio_equity` | valorisations à chaque clôture | `(job_id, sequence)` |

Chaque table porte `schema_version=1`. Les IDs métier sont uniques par job, les
séquences non négatives et les champs obligatoires `NOT NULL`. Les exécutions
référencent leur ordre et les trades leurs exécutions. Les tables filles
référencent le run, lié à `backtest_jobs` avec `ON DELETE CASCADE`.

La clé `(job_id, sequence)` couvre les pages trades/equity. Les indexes
additionnels sont `idx_portfolio_executions_order(job_id, order_id)` et
`idx_portfolio_equity_time(job_id, timestamp, sequence)`. Le filtre temporel
public reste reporté.

`SCHEMA_VERSION=8` et `MIGRATION_8` suivent `schema_migrations`. La migration est
additive, idempotente, sans dépendance externe ni suppression historique.

## Décimaux et timestamps

Les valeurs comptables sont des `TEXT`, jamais des `REAL` :

```text
Decimal("100.00") → "100"
Decimal("0.0010") → "0.001"
Decimal("-0") → "0"
```

La lecture reconstruit directement un `Decimal` fini, sans `float`. Les
timestamps sont ISO 8601 UTC, six chiffres de microsecondes et suffixe `Z`. Une
date naïve est refusée. L'ordre canonique repose sur `sequence`.

## Transaction, lots, annulation

`replace_simulation_result` ouvre `BEGIN IMMEDIATE`, supprime l'ancien run,
insère métadonnées, ordres, exécutions, trades et equity, contrôle les quatre
compteurs puis commit. Les `executemany` utilisent des lots de 1 000.

Une erreur, incohérence ou annulation provoque un rollback complet. Le `DELETE`
étant transactionnel, un remplacement invalide préserve l'ancien run. Aucun
état `writing` n'est visible. Configuration, métriques et position finale sont
de petits JSON canoniques bornés ; les collections détaillées ont leurs tables.

L'ordre de finalisation est :

```text
replay et analytics
→ simulation pure
→ persistance atomique
→ résumé public
→ artefacts et checkpoint final
→ statut completed
```

Une erreur de persistance devient `portfolio_persistence_failed`; le détail
SQLite reste dans les logs. Une annulation ou un échec après écriture supprime
le run avant publication du statut non final.

Après succès, `BacktestJob.portfolio_result` vaut `None`. La courbe n'est plus
dupliquée en mémoire.

## Redémarrage, reconstruction et checkpoints

Les checkpoints Phase 6.3 restent inchangés : la simulation est recalculée à la
fin, puis remplace atomiquement le run. Aucun portefeuille partiel n'est ajouté
au checkpoint.

`load_portfolio_simulation_result(job_id)` relit les cinq tables, contrôle les
compteurs et reconstruit exactement configuration, ordres, exécutions, trades,
equity, métriques et position finale. Les pages REST interrogent directement
leur table au lieu d'utiliser cette reconstruction. Une nouvelle instance du
repository retrouve les données après redémarrage.

Un job Phase 6.3 peut avoir un résumé avec `has_trades=true` sans run. Les routes
répondent `409 portfolio_details_legacy_unavailable`, jamais une liste vide. Un
run moderne sans trade renvoie bien `items=[]` et `total=0`.

## API et limites

Les routes suivent le préfixe existant, sans segment `/jobs` :

```text
GET /api/backtests/{job_id}/portfolio
GET /api/backtests/{job_id}/trades?offset=0&limit=100
GET /api/backtests/{job_id}/equity?offset=0&limit=100
GET /api/backtests/{job_id}/equity?mode=sampled&max_points=1000
GET /api/backtests/{job_id}/trades/export.csv
GET /api/backtests/{job_id}/equity/export.csv
```

La métadonnée expose versions, moteur, quote asset, résumé,
`details_status=complete`, compteurs et `available_after_restart=true`.

- trades : `offset >= 0`, défaut 100, `1 <= limit <= 500` ;
- equity brute : défaut 100, `1 <= limit <= 1000` ;
- sampled : `offset=0`, `4 <= max_points <= 2000`.

Les pages SQL utilisent `ORDER BY sequence LIMIT ? OFFSET ?`. Le mode sampled
expose `sampled=true` et `source_point_count`.

| Situation | HTTP | Code |
|---|---:|---|
| job inconnu | 404 | contrat historique |
| portefeuille absent | 404 | `portfolio_not_requested` |
| job non terminé/annulé/échoué | 409 | `portfolio_job_not_completed` |
| résumé historique sans détails | 409 | `portfolio_details_legacy_unavailable` |
| détails modernes absents | 409 | `portfolio_details_unavailable` |
| paramètres invalides | 422 | validation ou `invalid_pagination` |

## Échantillonnage

Un balayage `fetchmany(1000)` des seules colonnes utiles trouve le premier
maximum global d'equity et de drawdown. La sélection contient premier point,
dernier point, ces deux extrema, puis des séquences régulièrement espacées.
Une seconde requête charge seulement les séquences choisies.

Aucune interpolation ni valeur inventée, aucun objet Pydantic pendant le
balayage, ordre final croissant et résultat déterministe. Les extrema globaux
sont conservés, pas nécessairement chaque extremum local.

## Exports v1

Les `StreamingResponse` utilisent les itérateurs du repository par lots de
1 000. L'equity complète n'est jamais matérialisée globalement. Une interruption
client ferme la connexion de lecture sans affecter la base.

`{job_id}-trades-v1.csv` :

```text
schema_version,job_id,trade_sequence,trade_id,position_id,symbol,quote_asset,
entry_observation_id,exit_observation_id,entry_time,exit_time,entry_price,
exit_price,quantity,entry_fee,exit_fee,gross_exit_proceeds,net_exit_proceeds,
realized_pnl,return_ratio,duration_bars,exit_reason
```

`{job_id}-equity-v1.csv` :

```text
schema_version,job_id,sequence,timestamp,cash,position_value,equity,
realized_pnl_cumulative,unrealized_pnl,fees_cumulative,drawdown_ratio
```

UTF-8, virgule, quoting `csv`, CRLF, timestamps UTC, décimaux canoniques et
cellule vide pour `None`. L'export equity est toujours brut et complet.

## Suppression, rétention, concurrence et limites

`delete_job` efface les cinq tables par cascade réellement active. Il n'existe
actuellement aucun TTL automatique pour les jobs de backtest :
`JOB_TTL_SECONDS` concerne les jobs scanner. Aucun scheduler n'est ajouté et
aucune expiration automatique de backtest n'est annoncée. Un nettoyage
administratif passant par `delete_job` bénéficie de la même cascade.

WAL, busy timeout et connexions courtes restent inchangés. Le remplacement prend
un verrou `BEGIN IMMEDIATE`; les exports sont des lectures. SQLite reste adapté
à l'application locale, mais espace disque, WAL, temps d'export et contention
doivent être surveillés sur plusieurs années minute.

Il n'y a pas de limite arbitraire du nombre de trades ou points. Les protections
sont les lots, l'absence de duplication mémoire, les pages bornées,
`max_points<=2000` et la suppression avec le job.

Les endpoints ordres/exécutions, filtre temporel, frontend, formulaire, résumé
visuel, graphique, table et boutons d'export sont reportés. La Phase 6.5 devra
consommer ces contrats dans une section distincte des outcomes.
