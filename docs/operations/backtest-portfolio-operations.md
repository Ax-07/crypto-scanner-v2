# Exploitation des simulations de portefeuille de backtest

## Stockage et migration

La base est celle configurée par `DATABASE_PATH`; l'application locale utilise
SQLite via `Database`. La migration applicative 8 crée :

- `backtest_portfolio_runs`;
- `backtest_portfolio_orders`;
- `backtest_portfolio_executions`;
- `backtest_portfolio_trades`;
- `backtest_portfolio_equity`.

Le run référence `backtest_jobs(id)` et toutes les tables filles utilisent
`ON DELETE CASCADE`. Vérifier la version :

```sql
SELECT MAX(version) FROM schema_migrations;
```

## Taille et WAL

Une equity minute annuelle approche 500 000 lignes. L'audit synthétique a
observé un fichier d'environ 91,4 Mo dans une base temporaire ayant aussi
contenu les cas petit et moyen. La taille réelle dépend des trades, chaînes
décimales et pages SQLite réutilisées.

Le mode est WAL, `synchronous=NORMAL`, `busy_timeout=5000`, connexions courtes.
Un WAL transitoire est normal pendant une écriture. Après fermeture des
connexions de l'audit, il était revenu à 0 sans checkpoint manuel. Ne modifier
les pragmas qu'après reproduction d'un problème.

## Rétention et suppression

Il n'existe aucun TTL automatique pour les backtests.
`JOB_TTL_SECONDS` concerne les jobs scanner. Les backtests s'accumulent jusqu'à
une suppression explicite via `DELETE /api/backtests/{job_id}` sur un job
terminal. La cascade supprime les détails portefeuille.

La suppression libère des pages internes mais ne réduit pas nécessairement la
taille du fichier. `VACUUM` est une opération administrative bloquante à
planifier séparément; elle n'est pas exécutée automatiquement.

Recommandation : définir une politique locale documentée (âge, taille ou
projets à conserver), lister les jobs puis supprimer explicitement les
éléments validés. Aucun scheduler n'est implémenté.

## Sauvegarde et restauration

Utiliser le mécanisme de sauvegarde SQLite existant
`app.cli.backup_database`, idéalement lorsque les écritures sont arrêtées.
Conserver ensemble le fichier cohérent produit par l'outil, la version de
l'application et la configuration.

Pour restaurer :

1. arrêter l'application;
2. conserver une copie de la base courante;
3. placer la sauvegarde au chemin `DATABASE_PATH`;
4. redémarrer pour appliquer uniquement les migrations manquantes;
5. vérifier `schema_migrations`, un job et ses compteurs portfolio;
6. tester une page et un export.

Ne pas copier seulement le fichier `-wal` ou `-shm`.

## Diagnostic d'un job

```sql
SELECT id, status, error, created_at, completed_at
FROM backtest_jobs WHERE id = ?;

SELECT schema_version, engine_version, order_count, execution_count,
       trade_count, equity_point_count, final_cash, final_equity
FROM backtest_portfolio_runs WHERE job_id = ?;

SELECT COUNT(*) FROM backtest_portfolio_trades WHERE job_id = ?;
SELECT COUNT(*) FROM backtest_portfolio_equity WHERE job_id = ?;
```

Comparer les quatre compteurs du run aux tables. Les routes `portfolio`,
`trades` et `equity` ne sont disponibles que pour un job `completed`.

Codes utiles :

- `portfolio_not_requested`;
- `portfolio_job_not_completed`;
- `portfolio_details_legacy_unavailable`;
- `portfolio_details_unavailable`;
- `portfolio_persistence_failed`;
- `invalid_pagination`.

Une erreur de persistance provoque un rollback, marque le job en échec et ne
publie aucune ligne partielle. La trace technique reste dans les logs; l'API
n'expose pas de stack trace.

## Exports

- `{job_id}-trades-v1.csv`;
- `{job_id}-equity-v1.csv`.

L'equity exportée est brute et complète. Pour les grands jobs, préférer
l'échantillonnage pour l'écran et réserver l'export complet au téléchargement.
Une interruption ferme la connexion de lecture et ne modifie pas les données.

## Commandes de validation

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall -q app
.\venv\Scripts\python.exe -m black --check app tests scripts
.\venv\Scripts\python.exe -m flake8 app tests scripts
.\venv\Scripts\python.exe -m mypy app
.\venv\Scripts\python.exe scripts\audit_portfolio_simulation.py
```

## Limites

SQLite reste adapté à l'usage local avancé, mais le temps d'export, la taille du
fichier, la contention et la mémoire du résultat moteur doivent être surveillés.
Il n'existe ni TTL de backtest, ni monitoring disque, ni filtre temporel
d'equity. Ces limites ne sont pas masquées par la Phase 6.6.

