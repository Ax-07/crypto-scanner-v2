# Audit de migration des signaux structurés — Phase 5.6

État vérifié le 29 juillet 2026 à partir du code du dépôt. Cet audit prépare une
future dépréciation, mais ne supprime aucun champ historique et ne modifie aucun
contrat backend.

## 1. Périmètre et méthode

L'audit couvre les contrats TypeScript/Zod, les API, les stores Zustand, les
pages et composants scanner, marché et backtest, leurs tests, ainsi que les
modèles, domaines, services et exports backend nécessaires à la comparaison.
Les documents de reprise ont été relus, puis confrontés au code actif.

État Git initial :

- branche `main`, `HEAD` `ed47282` ;
- commits précédents visibles : `ed47282`, `cecf0f9`, `f23d18e` ;
- `git diff --check` réussi ;
- arbre déjà non propre : modification utilisateur de
  `frontend/src/features/backtests/components/backtest-observations-table.tsx`
  (`break-words` remplacé par `wrap-break-word`), préservée par la mission ;
- Git requiert `safe.directory` dans cet environnement Windows ; les contrôles
  utilisent une option locale à la commande, sans changer la configuration ;
- aucun build, cache, `node_modules`, export applicatif ou rapport généré suivi ;
- la règle générique `backtests/` est compensée par
  `!frontend/src/features/backtests/` et `!frontend/src/features/backtests/**` ;
  les sources de la feature sont donc bien visibles par Git.

## 2. Matrice de l'état réel

| Fonctionnalité | Scanner | Marché | Backtest |
|---|---|---|---|
| Contrat `indicator_signals` | oui, `ScanResult` optionnel | oui, `SignalView` optionnel | oui, `SignalObservation` optionnel |
| Validation Zod | oui, enveloppe additive | oui, vues/messages stricts | oui, enveloppe additive |
| Conservation dans le store | oui, résultat complet | oui, snapshot complet REST/WS | oui, page d'observations |
| Résumé compact | oui | non, inutile dans les cartes dédiées | oui |
| Détail complet | oui, `Sheet` | oui, panneaux confirmed/provisional | oui, `Sheet` |
| Champ absent géré | oui, payload historique | oui, payload historique | oui, payload historique |
| Objet vide géré | oui, message distinct | oui, message distinct | oui, message distinct |
| Dictionnaire partiel | oui, sans synthèse | oui, sans synthèse | oui, sans synthèse |
| Statuts indisponibles | transmis aux cartes | transmis aux cartes | transmis aux cartes |
| Confluence affichée | score/grade historique | objet backend | facteurs/poids/contributions backend |
| Intensité expliquée | note commune | note commune + note trend | note commune + causalité |
| Ancien payload compatible | oui | oui | oui |
| Tests dédiés | oui | oui | oui |
| Responsive | table + `Sheet` | onglets mobile, 2 colonnes desktop | table + `Sheet` |
| Accessibilité | titre/description/focus/Échap | tablist clavier et titres | titre/description/focus/Échap/nav |

Les trois pages sont donc réellement intégrées. Le marché n'est pas une phase à
réaliser : `MarketSignalsSection` est monté dans `MarketPage` et lit séparément
les vues `confirmed` et `provisional`.

## 3. Architecture actuelle

`types/indicator-signals.ts` est le contrat canonique frontend.
`schemas/indicator-signals.ts` impose les six clés reconnues et les sept champs
stricts d'un signal. Scanner et backtest valident le champ dans des enveloppes
`.passthrough()` afin de conserver les données historiques. Le marché valide ses
vues et messages connus plus strictement. Le champ reste optionnel et non
nullable dans les trois flux.

Les stores ne possèdent aucun état global propre aux signaux :

- scanner : `ScanResult[]` complet après l'appel terminal ;
- marché : `MarketSnapshot` complet pour REST, `history` et `update` ;
- backtest : `SignalObservation[]` paginé.

La bibliothèque `components/indicator-signals/` rend les données reçues, fixe
l'ordre RSI/SMA/EMA/MACD/Bollinger/Stochastique et ne calcule ni décision, ni
confluence, ni recommandation.

## 4. Composants communs

| Composant | Props principales | Responsabilité | Utilisation et tests |
|---|---|---|---|
| `IndicatorStatusBadge` | `status`, `compact?`, `className?` | statut textuel, icône et style | utilisé par `IndicatorSignalCard`, testé via badges/cartes |
| `IndicatorDirectionBadge` | `direction`, `compact?`, `className?` | direction technique non prescriptive | cartes et résumés scanner/backtest, testé |
| `IndicatorStrength` | `value`, `showValue?`, `compact?`, `className?` | intensité 0–100 et progressbar | utilisé par la carte, tests dédiés |
| `IndicatorStrengthNote` | `className?` | convention pédagogique commune | scanner, marché, backtest, assertions transversales |
| `IndicatorSignalCard` | `indicator`, `signal`, options d'affichage | détail d'un signal et diagnostic d'indisponibilité | utilisé par le panneau, tests dédiés |
| `IndicatorSignalsPanel` | `signals`, compact/filtre/raison/message | ordre canonique et grille de cartes | utilisé dans les trois features, tests dédiés |

Les helpers communs sont :

- `summarizeIndicatorSignals` : compte uniquement les clés reçues ;
- `getIndicatorSignalsCollectionState` : distingue ancien payload, vide et
  collection disponible ;
- `formatIndicatorSignalsCollectionMessage` : produit un français correct selon
  le contexte ;
- `formatIndicatorDirectionCount` : accorde les compteurs ;
- les formatters préexistants de libellés et de `raw_value`.

## 5. Composants spécifiques conservés

| Composant | Props | Rôle spécifique | Utilisé / testé |
|---|---|---|---|
| `ScannerResultSignals` | `result` | résumé et ouverture locale du `Sheet` scanner | table scanner / oui |
| `ScannerResultSignalsSummary` | `signals` | résumé compact d'une cellule | scanner / oui |
| `ScannerResultSignalsDetails` | `result` | confluence historique et signaux du résultat | `Sheet` scanner / oui |
| `MarketSignalSnapshot` | `kind`, `snapshot`, `symbol`, `timeframe` | vue confirmed ou provisional | section marché / oui |
| `MarketSignalsSection` | `symbol`, `timeframe` | sélecteurs Zustand fins et onglets responsive | page marché / oui |
| `MarketConnectionStatus` | aucune | état réel de la socket et erreur persistante | page marché / oui |
| `BacktestObservationSummary` | `observation` | décision, confluence et résumé compact | table backtest / oui |
| `BacktestObservationDetails` | `observation`, `entryPolicy` | causalité, rejet, confluence et `Sheet` | table backtest / oui |
| `BacktestObservationsTable` | `job` | pagination et états réseau | page backtest / oui |
| `BacktestDecisionBadge` | `accepted`, `className?` | acceptation des filtres, jamais un trade | résumé/détail / oui |

Aucun de ces composants n'est inutilisé. Les recherches d'import confirment leur
montage réel ; aucune suppression ou fusion n'est proposée dans cette phase.

## 6. Duplications constatées et extractions réalisées

Duplications réelles :

1. scanner et backtest recalculaient séparément total, disponibles,
   indisponibles et directions ;
2. les trois détails testaient séparément `undefined` et `{}` avec des textes
   proches ;
3. scanner et backtest dupliquaient l'accord des directions ;
4. la convention pédagogique sur `strength` n'était pas un composant partagé et
   n'apparaissait pas explicitement dans le panneau marché.

Extractions réalisées :

- `indicator-signals-summary.ts` pour les compteurs, l'état de collection, les
  messages et l'accord des directions ;
- `indicator-strength-note.tsx` pour la phrase commune ;
- refactor des deux résumés et des trois détails vers ces primitives ;
- tests purs couvrant disponibilité, mélange, partiel, vide, non-mutation,
  direction neutre indisponible, états et contextes ;
- assertions de convention dans les tests scanner, marché et backtest.

## 7. Extractions volontairement refusées

- Pas de composant universel scanner/marché/backtest : leurs décisions,
  temporalités et contenus pédagogiques diffèrent.
- Pas de `SignalDetailsSheetLayout` : seuls scanner et backtest utilisent un
  `Sheet`. Leurs déclencheurs et contenus sont simples, et une extraction à deux
  consommateurs déplacerait peu de logique tout en compliquant la composition.
- Pas de formatter universel pour tous les nombres : un prix, une valeur brute,
  un facteur, un poids, un rendement et des bps ne partagent pas la même unité.
- Pas de résumé compact marché : la page possède déjà deux cartes de détail
  visibles ; ajouter un résumé dupliquerait l'information.
- Pas de refonte Zustand : les composants concernés utilisent déjà des sélecteurs
  par propriété. Aucune sélection manifestement trop large n'a été trouvée.

## 8. Convention des états

État structurel du dictionnaire :

| Entrée | État | Affichage |
|---|---|---|
| `undefined` | `legacy_absent` | « Les signaux structurés ne sont pas disponibles pour … » |
| `{}` | `empty` | « Aucun signal structuré n’a été produit pour … » |
| au moins une clé reconnue | `available` | clés reçues uniquement |

Une collection `available` peut ne contenir que des signaux
`insufficient_data`, `invalid_data` ou `disabled`. Ces statuts individuels ne
sont jamais confondus avec l'état de la collection. Une direction contractuelle
`neutral` portée par un statut indisponible n'est pas comptée comme un signal
neutre.

Le frontend ne convertit pas `undefined` en `{}`, ne fabrique pas de statut
`disabled` depuis la configuration et ne reconstruit aucun signal depuis les
champs historiques.

## 9. Conventions de libellés et d'intensité

La terminologie autorisée est « Intensité » ou « Intensité technique ».
`strength` représente une force conventionnelle selon les règles de
l'indicateur. Ce n'est ni une probabilité, ni une confiance, ni une fiabilité, ni
un taux de réussite, ni une chance de gain.

Note commune :

> L’intensité représente la force technique du signal selon les règles de
> l’indicateur. Elle ne représente pas une probabilité de gain.

Les notes spécifiques restent distinctes :

- scanner : opportunité technique filtrée et contexte historique séparé ;
- marché : le provisoire peut changer avant clôture et SMA/EMA ne remplacent pas
  le facteur historique `trend` ;
- backtest : signal, acceptation des filtres et outcomes futurs sont distincts,
  avec rappel anti-look-ahead et absence de portefeuille.

Les statuts sont « Disponible », « Données insuffisantes », « Données invalides »
et « Désactivé ». Les directions sont « Haussier », « Baissier » et « Neutre ».
Aucun texte d'achat ou de vente n'est produit.

## 10. Dates, nombres et unités

Inventaire réel :

| Valeur | Formatter | Convention |
|---|---|---|
| `raw_value` | `formatIndicatorRawValue` | `fr-FR`, précision par indicateur, aucune unité inventée |
| intensité | `IndicatorStrength` | ratio backend 0–1 affiché 0–100 |
| prix scanner | formatter local | `fr-FR`, 8 chiffres significatifs |
| prix marché/backtest | `Intl.NumberFormat` local | `fr-FR`, jusqu'à 8 décimales |
| confluence | formatters locaux | score `/100`, grade backend |
| timestamps | `toLocaleString("fr-FR")` dans les nouveaux composants | locale explicite |
| rendement | page backtest | ratio multiplié par 100 et suffixe `%` |
| frais/slippage | formulaire backtest | unité métier `bps`, inchangée |
| durée/horizon | backtest | nombre de bougies, inchangé |

Seuls les formatters strictement identiques de signaux ont été partagés. Aucune
devise, conversion monétaire ou unité supplémentaire n'est supposée.

## 11. Inventaire des champs historiques frontend

Les API scanner/backtest utilisent des enveloppes additives et ne revalident pas
chaque champ historique ; le marché les valide dans `api/market.ts`. Les stores
conservent l'objet métier entier plutôt que chaque champ séparément.

| Champ | Déclaration / flux | Affichage et tests | Équivalent structuré | Remplaçable ? / information conservée |
|---|---|---|---|---|
| `rsi` | scanner, marché, observation | table scanner, `MarketMetrics`, fixtures/tests | `rsi.raw_value` | partiellement ; scalaire utile aux anciens clients/CSV |
| `trend` | marché | `MarketMetrics`, tests marché | SMA/EMA | non ; classification historique mono-timeframe |
| `trend_score` | scanner, observation | table scanner, fixtures/tests | aucun exact | non ; agrégation multi-timeframes |
| `trend_states` | scanner, observation | détail historique scanner, tests | aucun exact | non ; dictionnaire multi-timeframes |
| `trend_net_score` | scanner, observation | table scanner, tests | aucun exact | non ; score signé multi-timeframes |
| `moving_averages` | scanner | contrat, CSV, tests | `sma/ema.raw_value` | non ; dictionnaire de périodes/timeframes |
| `macd` | scanner, marché | CSV, graphique/métriques, tests | `macd.raw_value` | non ; les séries/valeurs MACD restent plus riches |
| `macd_signal_type` | scanner | colonne, filtre, CSV, tests | `macd.direction/state` | partiellement ; vocabulaire du filtre |
| `bollinger` | marché | graphique/métriques | `bollinger.state/raw_value` | non ; vue legacy et bandes graphiques |
| `bb_position` | scanner | colonne, filtre, CSV, tests | `bollinger.state` | partiellement ; contrat de filtre |
| `stochastic` | marché | graphique/métriques | `stochastic.state/signal` | non ; séries `%K/%D` séparées |
| `stoch_signal` | scanner | colonne, filtre, CSV, tests | signal stochastique | partiellement ; contrat de filtre |
| `confluence_score` | scanner, observation | tableaux/détails, CSV, tests | aucun | non ; calcul backend distinct |
| `confluence_grade` | scanner, observation | tableaux/détails, CSV, tests | aucun | non |
| `confluence_breakdown` | scanner, observation | détail backtest, CSV scanner, tests | aucun | non ; contributions par facteur |
| `effective_weights` / `confluence_effective_weights` | backtest / scanner | détail backtest, CSV scanner, tests | aucun | non ; poids renormalisés |
| `availability` / `indicator_availability` | marché/backtest / scanner | métriques marché, recherche backtest, tests | statuts individuels partiels | non ; inclut `trend` et les indicateurs omis |

Champs associés également bloquants : `macd_signal`, `macd_histogram`,
`bb_upper`, `bb_middle`, `bb_lower`, `stoch_k`, `stoch_d`, `trends`,
`confluence_details`, `confluence_factors`, `configured_weights`, `raw_values` et
`classes`. Un unique `raw_value` structuré ne remplace pas une série ou un
dictionnaire complet.

## 12. Matrice de dépréciation

| Champ historique | Flux | Usage actuel | Équivalent structuré | Remplaçable ? | Condition préalable | Statut |
|---|---|---|---|---:|---|---|
| `rsi` | scanner/marché/backtest | UI, CSV scanner, contrats | `rsi.raw_value` | partiellement | clients et export versionnés | candidat futur |
| `trend` | marché | métriques/confluence | SMA/EMA partiels | non | nouveau contrat de tendance | non remplaçable |
| `trend_score` | scanner/backtest | filtre, UI, CSV | aucun | non | remplacement multi-TF | non remplaçable |
| `trend_states` | scanner/backtest | confluence, UI, persistance | aucun | non | contrat multi-TF | non remplaçable |
| `trend_net_score` | scanner/backtest | UI/persistance | aucun | non | contrat multi-TF | non remplaçable |
| `moving_averages` | scanner | CSV et valeurs multi-périodes | SMA/EMA `raw_value` | non | contrat de séries/périodes | non remplaçable |
| `macd` et lignes associées | scanner/marché | graphique, CSV, métriques | `macd.raw_value` | non | préserver les trois séries | non remplaçable |
| `macd_signal_type` | scanner | colonne, filtre, CSV | `macd.direction` | partiellement | filtre et CSV migrés | dépréciation bloquée |
| bandes Bollinger | scanner/marché | graphique, CSV, métriques | signal Bollinger | non | contrat de bandes | non remplaçable |
| `bb_position` | scanner | colonne, filtre, CSV | `bollinger.state` | partiellement | filtre et CSV migrés | dépréciation bloquée |
| séries stochastiques | scanner/marché | graphique, CSV, métriques | signal stochastique | non | préserver `%K/%D` | non remplaçable |
| `stoch_signal` | scanner | colonne, filtre, CSV | signal structuré | partiellement | filtre et CSV migrés | dépréciation bloquée |
| confluence score/grade | trois flux | UI, filtres/analyses, CSV | aucun | non | contrat dédié inchangé | non remplaçable |
| breakdown/poids/détails | trois flux | explication, analyses, CSV | aucun | non | remplacement complet | non remplaçable |
| availability | trois flux | diagnostics/recherche | statuts partiels | non | couvrir trend et indicateurs omis | non remplaçable |

Aucun champ n'est « supprimé ». « Candidat futur » signifie seulement qu'une
équivalence partielle mérite une étude après migration des consommateurs.

## 13. Filtres historiques bloquants

| Filtre | Options formulaire, type TS et Zod | Valeurs backend | Relation structurée |
|---|---|---|---|
| `filter_macd_signal` | `bullish`, `bearish`, `neutral` | même union `MacdSignal` | proche de `macd.direction`, pas migré |
| `filter_bb_position` | `oversold`, `near_oversold`, `neutral`, `near_overbought`, `overbought` | même union `BollingerPosition` | proche de `bollinger.state` |
| `filter_stoch_signal` | `oversold`, `overbought`, `bullish_cross`, `bearish_cross`, `neutral` | union historique équivalente | proche de `stochastic.signal/state` |

Le formulaire envoie `null` si aucune case n'est cochée. `ScanConfig`,
`scanConfigSchema`, le modèle backend et `check_signal_filters` consomment encore
ces vocabulaires. Le scanner et le replay passent explicitement
`macd_signal_type`, `bb_position` et `stoch_signal` aux filtres. Leur suppression
avant un contrat de filtre structuré compatible casserait configurations,
presets, scanner et replay.

### Matrice de migration des filtres — Phase 5.7

| Filtre | Valeurs exactes | Dimension de parité |
|---|---|---|
| `filter_macd_signal` | `bullish`, `bearish`, `neutral` | `direction` |
| `filter_bb_position` | `oversold`, `near_oversold`, `neutral`, `near_overbought`, `overbought` | `state` |
| `filter_stoch_signal` | `bullish_cross`, `oversold`, `neutral`, `bearish_cross`, `overbought` | `signal` |

Le Stochastique reste conceptuellement ambigu : les valeurs historiques
contiennent événements et zones. Le code actif recopie toutefois la
classification historique priorisée dans `stochastic.signal`; `state` conserve
la zone même pendant un croisement. L'adaptateur utilise donc `signal` pour
préserver exactement le booléen historique. Les nouvelles règles peuvent
combiner événement et état en `any`.

La Phase 5.7 ajoute `structured_signal_filters.version=1`, prioritaire par
indicateur. Une clé absente utilise le fallback legacy ; une clé présente avec
`conditions: []` neutralise explicitement ce filtre sans fallback.

Le dépôt ne contient aucun preset scanner, stockage local, configuration
scanner sérialisée dans l'URL ni persistance backend de `ScanConfig` à migrer.
Les jobs en mémoire conservent leur snapshot et les jobs historiques frontend
restent lisibles sans transformation.

## 14. Exports CSV

- Scanner : 23 colonnes historiques fixes. `indicator_signals` est
  intentionnellement absent ; les champs legacy sont la seule représentation
  exportée.
- Backtest : l'export `dataset=observations` sérialise tous les champs du modèle,
  et encode les dictionnaires/listes en JSON ; `indicator_signals` est donc
  présent dans une cellule JSON.
- Marché : aucun export de snapshot ou de signaux. Seul l'export de bougies
  existe et ne constitue pas un export des signaux.

Le CSV scanner bloque la dépréciation de ses colonnes historiques. Le CSV
backtest impose une stratégie de versionnement avant toute modification de
forme. Aucun format CSV n'a été changé ici.

## 15. Contrats Zod stricts

Les clés reconnues sont exactement `rsi`, `sma`, `ema`, `macd`, `bollinger` et
`stochastic`. Une clé inconnue ou un huitième champ dans un signal est rejeté.
Cette synchronisation stricte est volontairement conservée.

Ajout d'un nouvel indicateur :

1. définir calcul, statut et signal dans le domaine backend ;
2. l'ajouter au type domaine et au modèle Pydantic public ;
3. ajouter la clé au contrat TypeScript `IndicatorName` ;
4. ajouter la clé au schéma Zod strict ;
5. compléter ordre, libellé et format de valeur dans la configuration UI ;
6. ajouter tests domaine, Pydantic/OpenAPI, Zod, formatters et rendu ;
7. décider explicitement quels flux/features le produisent et l'affichent.

Il ne faut pas rendre le schéma permissif pour éviter cette procédure : un oubli
doit être détecté à la frontière réseau.

## 16. Sélecteurs Zustand

- scanner : `ScannerWorkspace` sélectionne chaque propriété/action séparément ;
  les composants de signaux reçoivent le résultat en props ;
- marché : `MarketSignalsSection` sélectionne séparément
  `snapshot.confirmed` et `snapshot.provisional` ;
- backtest : la table sélectionne individuellement page, total, offset,
  chargement, erreur et action.

Aucun nouveau composant lié aux signaux ne souscrit au store entier. Les objets
ne sont pas reconstruits dans les sélecteurs. Aucune optimisation n'a été
nécessaire.

## 17. Risques restants

- double calcul adaptateur/canonique du scanner, hors périmètre frontend ;
- absence de modèle Pydantic public pour le snapshot marché ;
- synchronisation manuelle obligatoire lors d'un septième indicateur ;
- divergence possible entre vocabulaire de filtre historique et futurs
  événements structurés ;
- CSV scanner incapable de transporter le contrat structuré ;
- tendance multi-timeframes sans équivalent structuré ;
- champs de confluence indispensables et indépendants de `strength` ;
- anciens clients externes non mesurés par une télémétrie, volontairement absente.

## 18. Plan de migration versionnée proposé

### D1 — Mesure et documentation

Maintenir cet inventaire, les tests d'anciens payloads et les équivalences. Aucun
changement de payload.

### D2 — Nouveaux consommateurs

Employer `indicator_signals` dans toute nouvelle interface, tout en conservant
les champs historiques pour filtres, exports, graphiques et clients existants.

### D3 — Marquage de dépréciation

Ajouter documentation, commentaires TypeScript et métadonnées OpenAPI lorsque
les candidats exacts sont choisis. Aucune suppression.

### D4 — Migration des filtres

Concevoir un contrat de filtre structuré versionné, accepter les anciennes
valeurs, migrer presets et tests, puis mesurer les deux chemins en parité.

### D5 — Migration des exports

Ajouter une version d'export ou des colonnes structurées stables sans modifier
silencieusement le CSV existant.

### D6 — Suppression majeure

Seulement dans une version majeure, après période de transition, migration des
clients/tests et preuve d'absence d'usage.

## 19. Critères bloquant toute suppression

Un champ historique ne peut être supprimé que si :

- aucun filtre, export, composant, store ou test de compatibilité ne l'utilise ;
- aucun client externe documenté ne l'utilise ;
- le contrat structuré conserve toute l'information ;
- la tendance multi-timeframes possède un remplacement réel ;
- les séries MACD, bandes Bollinger, `%K/%D` et détails de confluence ont un
  remplacement lorsqu'ils sont concernés ;
- une période de dépréciation a été respectée ;
- la rupture est annoncée dans une version majeure.

## 20. Recommandation de phase suivante

L'intégration marché étant présente, la suite frontend la plus logique est la
migration versionnée des trois filtres historiques vers un contrat structuré
compatible. Le double calcul de parité du scanner est une dette backend séparée
et ne doit pas être mêlé à cette migration frontend.

## 21. Validation de la Phase 5.6

Frontend :

| Commande | Résultat |
|---|---|
| `pnpm install --frozen-lockfile` | réussi après une première tentative sandbox expirée ; 335 paquets réutilisés, 0 téléchargé, lockfile inchangé |
| `pnpm exec vitest run src/components/indicator-signals` | 6 fichiers, 68 tests réussis |
| `pnpm exec vitest run src/features/scanner` | 3 fichiers, 21 tests réussis |
| `pnpm exec vitest run src/features/market` | 8 fichiers, 31 tests réussis |
| `pnpm exec vitest run src/features/backtests` | 5 fichiers, 21 tests réussis |
| `pnpm run typecheck` | réussi |
| `pnpm run lint` | réussi, aucun avertissement |
| `pnpm run test` | 37 fichiers, 213 réussis, 0 ignoré, 0 échoué |
| `pnpm run build` | réussi, 2 054 modules transformés |

Backend, sans modification de source :

- `backend/venv/Scripts/python.exe -m pytest -q` : 366 réussis, 1 ignoré,
  22 subtests réussis, 1 avertissement pandas préexistant sur la perte de
  nanosecondes dans `market_data.py`.
