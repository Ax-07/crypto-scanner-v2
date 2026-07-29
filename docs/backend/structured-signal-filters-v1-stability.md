# Stabilisation des filtres de signaux structurés v1

## 1. Périmètre

La Phase 5.8 fige `structured_signal_filters.version=1`, mesure sa parité avec
les trois filtres historiques et retire seulement les recalculs de contrôle
dont l'équivalence est couverte par des tests. Elle ne déprécie et ne supprime
aucun champ, filtre, export ou contrat public.

Les seuls indicateurs filtrables sont `macd`, `bollinger` et `stochastic`. Les
champs v1 sont `direction`, `signal`, `state` et `status`. `strength` et
`raw_value` ne font pas partie du filtre v1.

## 2. Règles figées

- `version` est obligatoire et vaut exactement `1`.
- `indicators` accepte uniquement `macd`, `bollinger` et `stochastic`.
- `direction` accepte `bullish`, `bearish` et `neutral`.
- `status` accepte `available`, `insufficient_data`, `invalid_data` et
  `disabled`.
- `signal` et `state` acceptent une chaîne non vide après trim. Leur vocabulaire
  n'est pas fermé par indicateur en v1.
- `values` est une liste non vide et sans doublon. Ses valeurs sont combinées
  en OR.
- `match` vaut `all` ou `any` et combine les conditions du groupe.
- Les groupes d'indicateurs sont combinés en AND.
- Un groupe non vide sans condition `status` exige implicitement un signal
  `available`.
- Un groupe vide réussit sans lire le signal et neutralise le fallback legacy
  de cet indicateur.
- Une clé structurée présente est prioritaire sur le filtre legacy du même
  indicateur. Une clé absente reçoit son fallback legacy éventuel.
- Un contrat structuré globalement vide n'ajoute aucun filtre.
- Une version, un indicateur, un champ ou une clé d'objet inconnus sont rejetés.

Pydantic fournit les defaults internes `indicators={}`, `match="all"` et
`conditions=[]`. Les payloads officiels gardent néanmoins `match` et
`conditions` explicites ; le schéma Zod les exige lorsqu'un groupe existe.

## 3. Exemples JSON

Minimal :

```json
{"version": 1, "indicators": {}}
```

MACD :

```json
{
  "version": 1,
  "indicators": {
    "macd": {
      "match": "all",
      "conditions": [
        {"field": "direction", "values": ["bullish"]}
      ]
    }
  }
}
```

Bollinger, état OU événement :

```json
{
  "version": 1,
  "indicators": {
    "bollinger": {
      "match": "any",
      "conditions": [
        {"field": "state", "values": ["oversold"]},
        {"field": "signal", "values": ["lower_band_reentry"]}
      ]
    }
  }
}
```

Statut explicite :

```json
{
  "version": 1,
  "indicators": {
    "macd": {
      "match": "all",
      "conditions": [
        {"field": "status", "values": ["available"]},
        {"field": "direction", "values": ["bullish"]}
      ]
    }
  }
}
```

## 4. Matrice de parité legacy

| Indicateur | Valeurs historiques | Dimension v1 | Combinaisons testées |
|---|---|---|---|
| MACD | `bullish`, `bearish`, `neutral` | `direction` | `None`, vide, chaque singleton, toutes les paires, les trois |
| Bollinger | `oversold`, `near_oversold`, `neutral`, `near_overbought`, `overbought` | `state` | `None`, vide et les 31 sous-ensembles non vides |
| Stochastique | `bullish_cross`, `oversold`, `neutral`, `bearish_cross`, `overbought` | `signal` | `None`, vide et les 31 sous-ensembles non vides |

Pour chaque sous-ensemble, chaque classification possible est évaluée par
`check_signal_filters`, convertie avec `legacy_filters_to_structured`, puis
réévaluée par `check_structured_signal_filters`. Tous les booléens doivent être
identiques. L'oracle reste exclusivement dans
`backend/tests/test_structured_signal_filters_v1_contract.py`.

## 5. Priorité, fallback et groupes vides

Le fallback est résolu séparément pour chaque indicateur. Un MACD structuré ne
neutralise donc pas un filtre Bollinger ou Stochastique legacy. En cas de
conflit, le groupe structuré gagne. Une clé présente avec `conditions: []`
neutralise volontairement le filtre correspondant, même si le champ legacy
contient des valeurs. Cette règle est testée pour les trois indicateurs.

## 6. Statuts indisponibles

Sans condition `status`, `insufficient_data`, `invalid_data` et `disabled` ne
peuvent pas satisfaire une condition métier, même si leur direction neutre
semble correspondre. Une condition de statut explicite peut cibler chacun des
quatre statuts.

Un indicateur absent ne satisfait pas un groupe non vide. Pour rendre
`status=["disabled"]` filtrable, le scanner et le replay créent une vue locale
synthétique. Cette vue ne modifie pas `indicator_signals` et aucun signal
`disabled` artificiel n'est ajouté au payload public.

## 7. Compatibilité Stochastique

Le legacy Stochastique lit strictement `IndicatorSignal.signal`, jamais
`state`. Les croisements sont prioritaires dans la classification historique :
un `bullish_cross` survenu en zone `oversold` ne doit pas satisfaire le filtre
legacy `["oversold"]`. Une règle v1 nouvelle peut toutefois combiner événement
et zone avec deux conditions en `any`.

## 8. Tests de contrat

Les suites dédiées sont :

- `backend/tests/test_structured_signal_filters_v1_contract.py` : payloads JSON
  officiels, rejets, matrice exhaustive, classifications, statuts, `all`/`any`,
  priorité, fallback, groupes vides et fingerprints ;
- `backend/tests/test_structured_signal_filters.py` : moteur pur et régressions
  Phase 5.7 ;
- `backend/tests/test_scanner_service.py` : parité de décision au niveau service,
  payloads, désactivation, arrêt après filtre et compteurs d'appels ;
- `frontend/src/schemas/structured-signal-filters-v1.test.ts` : miroir JSON Zod,
  ancienne configuration et coexistence.

## 9. Cartographie des calculs scanner

État avant Phase 5.8 :

| Calcul | Moteur canonique | Adaptateur scanner | Payload scanner | Filtre | Autre besoin | Redondance mesurée |
|---|---:|---:|---:|---:|---|---:|
| RSI | oui | oui | oui | seuil RSI | signal/confluence | second passage + un recalcul interne canonique |
| MACD | oui | oui | trois scalaires + classe | legacy/v1 | confluence/divergences | second passage |
| Bollinger | oui | oui | trois bandes + classe | legacy/v1 | confluence | second passage |
| Stochastique | oui | oui | `%K`, `%D` + classe | legacy/v1 | confluence | second passage |
| SMA/EMA | oui | oui | valeurs multi-TF | tendance | score multi-TF | second passage |
| `build_indicator_signals` | oui | oui | oui | v1 | confluence | second passage |
| Confluence | oui | oui | oui | seuil | tri/détails | second passage |

L'adaptateur est nécessaire aux scalaires et séries historiques de
`ScanResult`, à la tendance multi-timeframes, aux filtres précoces et au CSV.
Le second appel à `evaluate_information_set` utilisait les mêmes bougies closes,
paramètres et instant, sans nouvel appel réseau ; sa fonction supplémentaire
était le contrôle runtime de parité.

## 10. Optimisations réalisées

Le scanner effectue désormais un seul passage :

1. il réutilise la série RSI déjà calculée pour sa dernière valeur et pour
   `IndicatorSignal` ;
2. il construit `indicator_signals` dans l'adaptateur et le place directement
   dans `ScanResult` ;
3. il ne rappelle plus `evaluate_information_set` uniquement pour comparer la
   décision ;
4. le moteur canonique réutilise lui aussi sa série RSI pour la dernière valeur,
   au lieu de rappeler `calculate_rsi` ;
5. si RSI/MACD/Bollinger/Stochastique sont tous désactivés, le builder n'est pas
   appelé.

La parité supprimée de la production est remplacée par un oracle de service qui
exécute les deux chemins sur les mêmes bougies et compare acceptation, classes
legacy et `indicator_signals`.

## 11. Comptage d'appels

Mesure déterministe de test : un symbole, 220 bougies `4h`, tous les indicateurs
actifs, SMA `[5, 8]`, EMA `[5, 8]`, un seul timeframe MA et confluence active.

| Appel | Avant | Après |
|---|---:|---:|
| `calculate_rsi` | 3 | 1 |
| `calculate_macd` | 2 | 1 |
| `calculate_bollinger_bands` | 2 | 1 |
| `calculate_stochastic` | 2 | 1 |
| `calculate_sma` | 4 | 2 |
| `calculate_ema` | 4 | 2 |
| `build_indicator_signals` | 2 | 1 |
| `evaluate_information_set` depuis le scanner | 1 | 0 |
| fetch OHLCV primaire | 1 | 1 |

Les nombres SMA/EMA sont proportionnels au nombre de périodes et timeframes.
Le test n'impose aucun temps mural et ne présente donc pas une machine locale
comme une garantie universelle. Il vérifie aussi qu'un rejet RSI n'entraîne
aucun calcul MACD/Bollinger/Stochastique ni builder.

## 12. Optimisations refusées

- Aucun champ public interne n'a été ajouté à `ScanResult` ou
  `SignalObservation`.
- Les séries MACD, bandes, `%K/%D` et moyennes n'ont pas été supprimées : elles
  alimentent encore les champs historiques et le CSV.
- La tendance multi-timeframes n'a pas été remplacée par SMA/EMA structurés.
- Le Stochastique legacy n'a pas été remappé vers `state`.
- Aucun mode diagnostic runtime ni réglage d'environnement n'a été ajouté : les
  tests suffisent.
- L'adaptateur scanner et le moteur de replay n'ont pas été fusionnés dans une
  nouvelle architecture.

## 13. Contrats publics et exports

La forme de `ScanResult`, `ScanJob`, `SignalObservation`, `MarketSnapshot`, des
WebSockets et des CSV n'est pas modifiée. Les champs
`filter_macd_signal`, `filter_bb_position`, `filter_stoch_signal`,
`macd_signal_type`, `bb_position` et `stoch_signal` restent présents. Aucun
fichier applicatif marché ou backtest frontend n'est modifié par la Phase 5.8.

## 14. Fingerprints

Le fingerprint trie les clés JSON et conserve l'ordre des listes. Les
fingerprints figés par les tests sont :

- legacy sans champ structuré :
  `sha256:17f402455510a523e8557cf7d9ba091aca0d8338a563ca0b51421d02d23bd237` ;
- structuré :
  `sha256:804665319a48a8120d39d3ef6113e245f2f8384f4edc0c97a868fc6e9802ff6b` ;
- mixte avec groupe vide :
  `sha256:47bad9c58f6ce1b54790c232005510cf1550bd62493d6d6e571d94781a28c42b`.

Le champ structuré absent reste exclu, ce qui préserve le fingerprint legacy.
Deux configurations sémantiquement équivalentes, l'une legacy et l'autre
structurée, ont volontairement des fingerprints différents : leur
représentation et leur politique de priorité ne sont pas identiques. Les
doublons v1 sont rejetés. Inverser l'ordre de deux valeurs valides modifie le
fingerprint même si la condition OR reste équivalente.

## 15. Frontend et absence de presets

Zod accepte les exemples officiels, le contrat partiel, le groupe vide et la
coexistence, puis rejette versions, indicateurs, champs, valeurs vides et
doublons inconnus. Une ancienne configuration sans champ structuré reste
valide. Le formulaire, le store et l'API conservent les deux familles de champs.

La recherche confirme l'absence de preset scanner persistant, de stockage local,
de configuration scanner dans l'URL et de persistance backend de `ScanConfig`.
Aucune migration de preset et aucun nouveau mécanisme de persistance ne sont
donc nécessaires.

## 16. Limites et impact

Le scanner et le replay conservent deux assemblages fonctionnels distincts.
Leur parité est maintenant contrôlée en tests, pas en production. Il n'existe
pas de télémétrie d'usage des anciens clients, volontairement. Les vocabulaires
libres de `signal` et `state` permettent des événements futurs compatibles,
mais une fermeture ou un changement de sens nécessiterait une nouvelle version.

L'impact attendu est une réduction déterministe des calculs CPU par symbole,
sans fetch supplémentaire, sans changement de tri, de progression, de résultat
public ou de CSV.

## 17. Politique de changement v1

- Toute modification incompatible exige une nouvelle version.
- Un champ existant ne change pas de sens.
- Une dimension de filtre qui modifie la validation appartient à une version
  ultérieure.
- `strength` et `raw_value` restent hors v1.
- Une version inconnue reste rejetée.
- Les filtres historiques restent acceptés pendant la transition.
- Aucun champ legacy n'est supprimé dans v1.

## 18. Critères avant toute dépréciation

Une dépréciation future exige au minimum :

1. une période de transition annoncée ;
2. une mesure réelle des consommateurs, sans inventer de télémétrie ici ;
3. une stratégie versionnée pour le CSV et les clients externes ;
4. la parité maintenue sur toutes les classifications historiques ;
5. un remplacement complet des informations publiques concernées ;
6. des tests de jobs anciens et mixtes ;
7. une décision explicite sur une éventuelle v2.

La prochaine phase doit être choisie d'après ces mesures : préparer v2 si de
nouvelles dimensions strictes sont nécessaires, organiser une dépréciation
officielle si les consommateurs ont migré, ou poursuivre les optimisations
internes seulement lorsqu'une nouvelle redondance est démontrée.

## 19. Validation finale

Backend :

- 540 tests passés, 1 ignoré, 27 subtests passés, 0 échec ;
- 2 warnings pandas préexistants dans `market_data.py` ;
- compileall, Black (100 fichiers), Flake8 et mypy (66 fichiers) réussis.

Frontend :

- installation figée réussie, 335 paquets réutilisés, aucun téléchargement et
  lockfile inchangé ;
- 41 fichiers de tests, 251 tests passés, 0 ignoré, 0 échec ;
- TypeScript, ESLint et build réussis ;
- 2 056 modules transformés par Vite.
