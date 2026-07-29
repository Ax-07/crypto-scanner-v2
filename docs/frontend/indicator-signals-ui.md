# Interface des signaux structurés

La Phase 5.2 fournit une bibliothèque de présentation réutilisable dans
`frontend/src/components/indicator-signals/`. Elle consomme les contrats canoniques
de `src/types/indicator-signals.ts`, sans store, appel API ou recalcul métier.
Depuis la Phase 5.3, le scanner la compose dans son tableau de résultats. Le marché
et le backtest ne l'utilisent pas encore.

## API publique

- `IndicatorStatusBadge({ status, compact?, className? })` affiche les quatre
  statuts avec texte, icône et style distinct.
- `IndicatorDirectionBadge({ direction, compact?, className? })` affiche une
  direction technique, jamais une recommandation d'achat ou de vente.
- `IndicatorStrength({ value, showValue?, compact?, className? })` borne
  visuellement la prop sur 0–100 et expose une barre de progression accessible.
- `IndicatorSignalCard({ indicator, signal, compact?, showReason?, className? })`
  présente un indicateur et adapte son contenu au statut.
- `IndicatorSignalsPanel({ signals, compact?, showUnavailable?, showReason?,
  className?, emptyMessage? })` ordonne un dictionnaire partiel et le rend dans
  une grille responsive.

Le barrel `index.ts` exporte aussi `INDICATOR_CONFIG`, `INDICATOR_LABELS`,
`INDICATOR_ORDER`, les tables de libellés et les fonctions pures de formatage.

## Métadonnées et libellés

L'ordre explicite est RSI, SMA, EMA, MACD, Bollinger, Stochastique. Il ne dépend
pas de l'ordre des clés du payload. Les événements et états connus sont traduits
en français. Une future valeur inconnue est humanisée sans interrompre le rendu :
`custom_signal` devient `Custom signal`. Les états composés avec `/` sont
formatés segment par segment.

Les statuts sont :

- `available` : Disponible, icône de validation ;
- `insufficient_data` : Données insuffisantes, icône d'horloge ;
- `invalid_data` : Données invalides, icône d'avertissement ;
- `disabled` : Désactivé, icône d'arrêt.

Les directions sont `bullish`/Haussier, `bearish`/Baissier et `neutral`/Neutre,
avec une flèche ascendante, descendante ou un tiret. Texte et icône rendent
l'information compréhensible sans la couleur.

## Intensité et valeur brute

`strength` est une intensité technique de 0 à 1, affichée de 0 à 100. Ce n'est ni
une probabilité, ni un taux de réussite, ni une garantie. Une prop hors plage est
bornée uniquement pour le rendu ; une valeur non finie devient visuellement 0.
La barre expose `aria-valuemin`, `aria-valuemax`, `aria-valuenow` et un nom comme
« Intensité technique : 75 sur 100 ».

`formatIndicatorRawValue` utilise explicitement `Intl.NumberFormat("fr-FR")` :

- RSI et Stochastique : jusqu'à deux décimales ;
- SMA, EMA et Bollinger : précision dynamique adaptée à l'ordre de grandeur ;
- MACD : précision dynamique renforcée pour les petites valeurs ;
- `null`, `NaN` et les infinis : `—`.

Le backend documente `raw_value` comme le RSI, la ligne MACD, la clôture pour
Bollinger, `%K` pour le Stochastique et la moyenne rapide pour SMA/EMA. L'UI garde
donc le libellé prudent « Valeur » et n'ajoute ni monnaie ni pourcentage.

## Statuts indisponibles et champs nuls

Un signal `available` peut afficher direction, événement, état, valeur, intensité
et raison. Une valeur brute nulle devient « Valeur : indisponible ». Les lignes
optionnelles `signal`, `state` et `reason` sont omises lorsqu'elles sont nulles :
le DOM n'affiche jamais `null`, une ligne vide ou un séparateur orphelin.

Pour les trois autres statuts, la carte affiche le diagnostic adapté et la raison
si elle existe. Elle masque direction, événement, état et intensité afin de ne pas
présenter la direction neutre contractuelle comme un calcul réellement effectué.

## Compact, responsive et accessibilité

Le mode compact réduit l'espacement, mais conserve le nom, le statut, la direction
si disponible, l'événement principal et l'intensité accessible. Il ne dépend ni
du survol ni d'un tooltip. Le panneau utilise une colonne, puis deux à partir de
`md` et trois à partir de `xl`. Les textes longs reviennent à la ligne et leur
contenu complet reste dans le DOM.

Chaque carte est un article nommé « Signal RSI », « Signal MACD », etc. Le panneau
est une région nommée, les icônes sont décoratives avec `aria-hidden`, et les
badges possèdent un nom accessible explicite.

Un objet `{}` affiche par défaut « Aucun signal structuré disponible. ». Si
`showUnavailable=false` filtre un dictionnaire non vide en totalité, le message
distinct « Aucun signal disponible avec le filtre actuel. » est utilisé. Le
composant ne crée jamais les indicateurs absents et ne mute pas l'objet reçu.

## Exemples

```tsx
import {
  IndicatorDirectionBadge,
  IndicatorSignalCard,
  IndicatorSignalsPanel,
  IndicatorStatusBadge,
  IndicatorStrength,
} from "@/components/indicator-signals"

<IndicatorStatusBadge status="available" />
<IndicatorDirectionBadge direction="bullish" />
<IndicatorStrength value={0.75} />

<IndicatorSignalCard
  indicator="rsi"
  signal={{
    status: "available",
    direction: "bullish",
    signal: "exit_oversold",
    state: "near_oversold",
    strength: 0.75,
    reason: "Le RSI vient de sortir de la zone de survente",
    raw_value: 31.4,
  }}
/>

<IndicatorSignalsPanel signals={signals} />
```

## Intégration dans le scanner — Phase 5.3

`features/scanner/components/scanner-results-table.tsx` conserve ses colonnes
historiques et ajoute une colonne non triable `Signaux`. Chaque cellule compose :

- `ScannerResultSignalsSummary`, qui décrit le nombre de signaux calculables,
  les indisponibilités et les directions reçues, sans recommandation globale ;
- `ScannerResultSignals`, qui porte uniquement l'état React local d'ouverture ;
- `ScannerResultSignalsDetails`, qui réutilise `IndicatorSignalsPanel` et affiche
  séparément le contexte historique de confluence.

Le bouton porte un nom tel que « Voir les signaux de BTC/USDC en 4h ». Il ouvre un
`Sheet` Radix/Shadcn avec titre et description accessibles, fermeture visible,
retour du focus et prise en charge d'Échap. Le panneau occupe toute la largeur sur
mobile, devient un panneau latéral large sur desktop et possède son propre scroll
vertical. La table conserve son scroll horizontal et la cellule reste compacte.

Les états de payload sont volontairement distincts :

- champ absent : « Les signaux structurés ne sont pas disponibles pour ce
  résultat. » ;
- objet vide : « Aucun signal structuré n'a été produit. » ;
- dictionnaire partiel : seuls les indicateurs présents sont rendus, dans l'ordre
  canonique ;
- statut indisponible : la carte reçue affiche `insufficient_data`,
  `invalid_data` ou `disabled` sans inventer un signal absent.

Le résumé n'utilise que `result.indicator_signals`. Il ne reconstruit aucun objet
depuis `job.config`, ne recalcule ni intensité ni confluence, et n'assimile jamais
l'intensité à une contribution ou une probabilité.

Les phases suivantes intégreront séparément le marché puis le backtest. La Phase
5.3 ne modifie ni leurs pages, ni leurs composants, ni les stores, routes, contrats
réseau ou graphiques.
