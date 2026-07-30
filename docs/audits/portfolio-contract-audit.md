# Audit des contrats portefeuille — Phase 6.6

## Sources comparées

Le contrôle couvre le domaine Python, les modèles Pydantic, l'OpenAPI généré,
la migration SQLite 8, les routes FastAPI, les types TypeScript, les schémas
Zod, les fixtures frontend, le store et les composants React.

Le test `backend/tests/test_portfolio_contract_audit.py` extrait le véritable
OpenAPI et verrouille les champs, types, nullabilités, littéraux et enums des
huit contrats publics demandés. Les tests `frontend/src/schemas/portfolio.test.ts`
valident les mêmes payloads à la frontière Zod.

## Matrice de traçabilité

| Notion | Domaine Python | Pydantic / OpenAPI | SQLite | TypeScript / Zod | Interface |
|---|---|---|---|---|---|
| Configuration | `PortfolioSimulationConfig` | `PortfolioSimulationConfigV1`, `PortfolioPositionSizingConfig` | `backtest_jobs.config_json`, `backtest_portfolio_runs.config_json` | `PortfolioSimulationConfig`, schémas stricts | formulaire activable |
| Résumé | `PortfolioMetrics` | `PortfolioSimulationSummary`, bloc du `BacktestJob` | `metrics_json`, compteurs du run | type et schéma summary | cartes, aucun recalcul |
| Run | `PortfolioSimulationResult` | `PortfolioRunMetadataV1` | `backtest_portfolio_runs` | `PortfolioRunMetadata` | disponibilité des détails |
| Ordre | `SimulatedOrder` | pas de route publique v1 | `backtest_portfolio_orders` | aucun type public dédié | non affiché |
| Exécution | `SimulatedExecution` | pas de route publique v1 | `backtest_portfolio_executions` | aucun type public dédié | non affichée |
| Trade | `SimulatedTrade` | `PortfolioTradeV1`, `PortfolioTradePage` | `backtest_portfolio_trades` | `PortfolioTrade`, schémas stricts | table et Sheet |
| Equity | `EquityPoint` | `PortfolioEquityPointV1`, `PortfolioEquityPage` | `backtest_portfolio_equity` | `PortfolioEquityPoint`, schémas stricts | graphique et résumé textuel |
| Export | itérateurs du repository | `StreamingResponse` | lecture par séquence | Blob non parsé | deux boutons CSV |

## Correspondance contractuelle

- Versions : littéral `1` partout.
- Enums : `percent_cash`, `next_open`, `force_close`,
  `validation_lost|end_of_test` identiques.
- Décimaux : `Decimal` dans le moteur, texte canonique SQLite, chaîne JSON,
  `string` TypeScript/Zustand; conversion en `number` seulement dans les
  formatters et le graphique.
- Nullabilité : seuls `win_rate`, `average_trade_return` et
  `exit_observation_id` sont nullables dans les contrats concernés.
- Timestamps : timezone exigée dans les DTO publics, stockage UTC `Z`,
  validation ISO avec fuseau dans Zod.
- Compteurs : entiers non négatifs. `open_position_count` est borné à 0 ou 1.
- Drawdown : ratio positif dans `[0,1]`,
  `(running_peak - equity) / running_peak`.
- Pagination : trades `1..500`, equity brute `1..1000`, échantillon
  `4..2000`; le modèle de réponse equity accepte jusqu'à 2 000.

## Divergences démontrées et corrections

### Nullabilité OpenAPI des décimaux obligatoires

Problème : un serializer Pydantic unique annoté `str | None` faisait apparaître
tous les décimaux du résumé comme nullables dans OpenAPI, alors que seuls deux
champs le sont dans TypeScript/Zod.

Reproduction : assertion sur le schéma OpenAPI réel dans
`test_openapi_exposes_optional_strict_portfolio_v1_contract`.

Correction : serializers séparés pour décimaux obligatoires et optionnels.
L'OpenAPI expose maintenant une chaîne non nullable pour les champs obligatoires.

### Bornes Pydantic plus faibles que Zod

Problème : Pydantic acceptait notamment un `trade_count` négatif, un drawdown
négatif, un prix de trade négatif et un cash négatif, tous rejetés par Zod.

Correction : bornes minimales/maximales, chaînes non vides et timestamps avec
fuseau ajoutés aux DTO publics. Les pages exposent aussi leur limite maximale.

### Type des décimaux de configuration

Problème : l'OpenAPI acceptait `number|string`, tandis que le contrat réseau
frontend exige une chaîne exacte.

Correction : schéma de validation public de type `string` et rejet explicite
des nombres JSON. Les formes textuelles équivalentes sont converties en
`Decimal`, puis canonisées pour le fingerprint et la sortie.

## Erreurs

| Code | HTTP | API | Store | Message UI / comportement | Test |
|---|---:|---|---|---|---|
| `portfolio_not_requested` | 404 | détail structuré | traduit | aucune simulation | API + frontend |
| `portfolio_job_not_completed` | 409 | détail structuré | traduit | attente de fin | API + frontend |
| `portfolio_details_unavailable` | 409 | détail structuré | traduit | détails indisponibles | frontend |
| `portfolio_details_legacy_unavailable` | 409 | détail structuré | traduit | résumé conservé, détails masqués | API + frontend |
| `portfolio_persistence_failed` | job `failed` | code dans `job.error` | erreur du job | texte réel, sans stack trace | rollback repository/manager |
| `invalid_pagination` | 422 | détail structuré ou validation FastAPI | traduit | page invalide | API |
| `job_not_found` | 404 | contrat historique « Backtest introuvable » | erreur générique | aucune stack trace | API historique |

`portfolio_persistence_failed` et `job_not_found` ne sont pas ajoutés à
`PortfolioApiErrorCode` : le premier appartient au cycle du job, le second au
contrat historique global, pas aux quatre routes de détails.

## Exports

Les colonnes et noms restent :

- `{job_id}-trades-v1.csv`;
- `{job_id}-equity-v1.csv`.

Timestamps UTC, décimaux canoniques, cellule vide pour `None`, UTF-8, CRLF et
ordre par séquence sont verrouillés. Les exports historiques observations,
outcomes et scanner n'ont pas été modifiés.

## Fingerprints

Le golden historique sans portefeuille reste
`sha256:911475d75c5eef8ac776128bc96e56de7657d936bc17b1336e897369b8291d87`.
Les représentations textuelles équivalentes produisent le même fingerprint.
Capital, frais, slippage, quote asset et présence du bloc participent au
fingerprint lorsqu'il existe.

## Divergences reportées

Aucune divergence bloquante restante n'a été observée sur les huit contrats.
Les ordres et exécutions restent volontairement sans endpoint/interface, le
filtre temporel equity reste reporté et aucune génération automatique de types
n'a été ajoutée.

Validation finale : 661 tests backend réussis, 1 ignoré, 27 subtests et deux
warnings pandas préexistants. Compileall, Black, Flake8 et mypy passent.
Frontend : 48 fichiers et 299 tests réussis; typecheck, lint et build passent.
