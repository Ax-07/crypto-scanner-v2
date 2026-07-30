# Audit end-to-end portefeuille — Phase 6.6

## Infrastructure

Le frontend utilise Vitest 4, jsdom et Testing Library. Aucun Playwright,
Cypress ou autre navigateur piloté n'est présent dans `package.json` ou les
configurations. Conformément au périmètre, aucune dépendance E2E n'a été ajoutée.

Il n'y a donc **aucun scénario navigateur réel** dans cette phase. Les scénarios
ci-dessous sont des scénarios DOM intégrés et cette limite est volontairement
explicite.

## Scénario principal simulé

`frontend/src/pages/backtests-page.test.tsx` couvre dans une seule navigation :

1. résultat historique et section « Analyse des rendements futurs »;
2. configuration portefeuille réelle;
3. résumé public;
4. equity échantillonnée;
5. trades déjà paginés par le store;
6. ouverture puis fermeture clavier-compatible du détail;
7. déclenchement séparé des exports trades et equity;
8. présence simultanée des outcomes et du portefeuille, sans assimilation.

Les tests existants couvrent aussi l'activation du switch, la dérivation de
l'actif de cotation, la saisie des pourcentages et le payload exact envoyé.

## Scénarios supplémentaires

| Scénario | Couverture |
|---|---|
| Job sans portefeuille | aucune section et aucun endpoint portefeuille |
| Job en cours | configuration et attente, aucun résumé inventé |
| Job annulé | aucun résultat final |
| Job échoué | erreur réelle du job |
| Job legacy | résumé visible, avertissement, détails/exports masqués |
| Zéro trade moderne | message vide distinct du legacy |
| Réponse tardive d'un autre job | metadata, trades, equity et erreurs ignorés |
| Export HTTP en erreur | `ApiError`, message utilisateur, aucun parsing CSV |
| Graphique démonté | désabonnement et `chart.remove()` vérifiés |
| Sheet | ouverture locale, Échap et retour du focus couverts par les tests |

## Accessibilité

- Switch nommé, label visible et description.
- Champs reliés à leur description et `aria-invalid`.
- Sections titrées; alertes pour les erreurs.
- Pagination dans un `nav` nommé.
- Gains/pertes portent un signe et un texte, jamais seulement une couleur.
- Drawdown nommé positivement.
- Le graphique a un rôle image, un nom accessible et un résumé textuel avec
  equity initiale/finale, drawdown, points affichés et points source.
- Le Sheet utilise Radix, fournit un bouton Fermer et restitue le focus.
- Les boutons d'export ont un libellé textuel et un état désactivé pendant le
  téléchargement.

Limite : aucun audit automatisé de contraste pixel ni lecteur d'écran réel n'a
été effectué.

## Responsive

Inspection des classes pour 320, 375, 768, 1024 et 1440 px :

- formulaire et cartes en une colonne puis grilles `sm`, `md`, `xl`;
- boutons d'export empilés puis en ligne;
- table dans `overflow-x-auto`;
- pagination avec `flex-wrap`;
- Sheet `w-full` puis `sm:max-w-4xl`;
- graphique `w-full`, hauteur fixe et `autoSize`.

Aucun débordement global n'est introduit par ces composants. Limite : jsdom ne
calcule pas la mise en page CSS; aucune capture dans un navigateur réel n'est
disponible.

## Localisation

Les formatters emploient `fr-FR`, séparateurs français, pourcentages, signes et
actif de cotation explicite sans symbole monétaire inventé. Les raisons de
sortie sont traduites. Les payloads et CSV restent indépendants de la locale.

## Résultat

Les scénarios DOM sont verts. La validation frontend complète a réussi avec
48 fichiers et 299 tests, sans échec ni test ignoré. TypeScript, ESLint et le
build Vite (2 065 modules transformés) passent également. L'absence d'un vrai
navigateur reste une limite de validation, pas un succès E2E navigateur.
