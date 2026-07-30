# Interface de simulation de portefeuille v1 — Phase 6.5

## Activation et configuration

La section « Simulation de portefeuille » du formulaire utilise React Hook Form,
Zod et les composants `Field`. Le switch est désactivé par défaut. Lorsqu'il
reste désactivé, `portfolio_simulation` est absent du POST : aucune valeur
proposée localement n'est présentée comme la configuration d'un ancien job.

Les valeurs proposées pour un nouveau backtest sont :

- capital initial : `10000`;
- taille : `100` % du cash;
- frais : `0,1` % dans l'UI, soit `"0.001"` sur le réseau;
- slippage : `0` %;
- exécution : `next_open`;
- fin : `force_close`.

La v1 est mono-symbole, `every_bar`, spot long-only et limitée à une position.
Ces politiques fixes sont expliquées plutôt qu'affichées dans des menus à une
seule option. Pour un symbole `BASE/QUOTE`, l'activation propose la partie
`QUOTE`, en majuscules, tout en la laissant modifiable.

`percentageInputToRatioString` accepte la virgule française et le point,
supprime les espaces et refuse notation exponentielle, signe négatif et formes
ambiguës. Le mapper pur `buildPortfolioSimulationPayload` normalise l'actif,
les décimaux et les constantes v1 sans muter le formulaire.

## Contrats et précision

`src/types/portfolio.ts` conserve tous les montants et ratios réseau en
`string`. `src/schemas/portfolio.ts` interdit les clés inconnues, versions et
enums inconnus, timestamps sans fuseau, compteurs négatifs, NaN, infinis,
exposants et chaînes décimales invalides.

Les helpers d'affichage utilisent `Intl.NumberFormat("fr-FR")`. Le capital est
toujours suffixé par son `quote_asset` (`10 000 USDC`, `5 000 EUR`) sans
conversion ni symbole monétaire implicite. Une conversion en `number` est
effectuée seulement pour le rendu ; l'objet réseau stocké n'est jamais modifié.

## Chargement et store

Le résumé borné inclus dans le job s'affiche immédiatement. Une fois un job
portefeuille `completed`, le store charge les métadonnées. Il ne contacte aucun
endpoint portefeuille pour un job historique, en cours, annulé ou échoué.

Les états metadata, trades et equity ont chacun leurs données, chargement et
erreur. Chaque réponse vérifie encore l'identifiant du job courant avant
d'écrire dans Zustand, afin qu'une réponse tardive d'un ancien job soit ignorée.
Changer de job ou lancer un replay remet tous les états portefeuille à zéro.

Les codes connus `portfolio_not_requested`, `portfolio_job_not_completed`,
`portfolio_details_unavailable`, `portfolio_details_legacy_unavailable` et
`invalid_pagination` sont traduits. Une erreur de métadonnées ne masque pas le
résumé déjà présent dans le job.

## Résumé et séparation des outcomes

Les cartes affichent capital initial, equity finale, profit net, rendement
total, drawdown maximal positif, frais, trades, win rate, exposition, P&L
réalisé/latent et positions ouvertes. Le texte précise que le P&L latent est
valorisé au close sans frais de sortie hypothétiques.

La section « Analyse des rendements futurs » décrit des mesures indépendantes
après chaque observation. La section « Simulation de portefeuille » décrit une
séquence de positions faisant évoluer un capital fictif. Aucune performance
n'est attribuée à RSI, MACD ou un autre indicateur.

## Equity et échantillonnage

`PortfolioEquityChart` réutilise `lightweight-charts`. Il affiche equity et cash
en lignes, puis le drawdown positif en histogramme. La requête est toujours :

```text
GET /api/backtests/{id}/equity?mode=sampled&max_points=1000
```

Le backend conserve l'equity brute et garantit que l'échantillon contient les
extrema globaux d'equity maximale et de drawdown. L'interface n'affiche pas un
minimum global non garanti. Le résumé textuel fournit equity initiale/finale,
drawdown maximal, points affichés et points source. L'export equity reste brut
et complet.

## Trades, détail et pagination

Les trades sont demandés par pages de 50, dans l'ordre `sequence` reçu. Les
colonnes montrent dates, prix, P&L signé, rendement, durée et raison de sortie.
Les raisons `validation_lost` et `end_of_test` deviennent « Perte de validation »
et « Fin du backtest ».

Le `Sheet` de détail affiche les valeurs déjà chargées, identifiants
d'observations, frais et produits. Son ouverture ne déclenche aucune requête.
Un `exit_observation_id=null` est présenté comme une clôture administrative.
Les observations hors de la page locale ne sont ni inventées ni rechargées.

## Exports

Les boutons trades et equity utilisent le client HTTP, lisent le nom de fichier
dans `Content-Disposition`, créent une URL objet temporaire, déclenchent le
téléchargement puis révoquent l'URL. Le CSV n'est jamais parsé dans React. Les
exports historiques restent inchangés.

## Compatibilité et états

- bloc absent : aucune section complète et aucun appel portefeuille;
- job en cours : configuration réelle et attente, aucun résultat inventé;
- annulé : aucun résultat final;
- échoué : erreur du job, aucun résumé périmé;
- Phase 6.3 legacy : résumé conservé, avertissement, pas de courbe, table ou export;
- Phase 6.4 moderne sans trade : table vide explicite, distincte du legacy;
- Phase 6.4 moderne : interface complète.

## Responsive et accessibilité

Le formulaire et les cartes passent d'une colonne mobile à une grille desktop.
Le graphique est auto-dimensionné. La table garde un scroll horizontal et la
pagination se replie. Le `Sheet` occupe toute la largeur sur mobile et atteint
`sm:max-w-4xl` sur desktop.

Le switch et les champs ont des noms et descriptions associés, les erreurs sont
annoncées, les alertes utilisent `Alert`, la pagination est nommée, le détail
inclut les dates dans son nom accessible et Radix gère Échap et le retour du
focus. Gains/pertes ont un signe et un texte ; le graphique possède un résumé
textuel et n'est jamais l'unique source du résultat.

## Limites restantes

L'equity brute reste côté backend. Aucun TTL automatique des jobs de backtest
n'est actif. Les ordres et exécutions n'ont pas encore d'interface publique
dédiée. Il n'existe ni short, levier, stop, take profit, multi-actifs, filtre
temporel d'equity ou résultat partiel public.

La Phase 6.6 doit auditer transversalement les grands volumes, renforcer les
scénarios end-to-end et vérifier la cohérence backend/frontend sans nouvelle
fonctionnalité majeure.

## Guide utilisateur

Le capital est fictif et exprimé dans l'actif de cotation affiché, par exemple
USDC pour `BTC/USDC`. La taille de position est la part du cash disponible
engagée à chaque entrée; elle n'ajoute ni levier ni emprunt.

Les frais sont appliqués à l'achat et à la vente. Le slippage dégrade le prix
dans les deux sens. Une décision prise à la clôture ne peut être exécutée qu'à
l'ouverture de la bougie suivante. La stratégie est spot, long-only, avec une
seule position; une position encore ouverte à la fin est clôturée au dernier
close.

L'equity est la somme du cash et de la valeur de la position. Le P&L réalisé
vient des trades fermés; le P&L latent valorise une position ouverte sans
anticiper ses frais de sortie. Le drawdown est le recul positif depuis le plus
haut d'equity : 0,12 signifie 12 %.

Les trades forment une séquence qui fait évoluer le capital. Les outcomes sont
différents : ils mesurent séparément ce qui arrive après chaque observation et
ne sont ni des ordres ni des trades. L'écran utilise une equity échantillonnée;
l'export equity CSV contient toujours la série brute complète.

La Phase 6.6 a validé le contrat, les réponses tardives du store, le nettoyage
du graphique et un volume de 500 000 points côté persistance. Les détails sont
dans `docs/audits/`.
