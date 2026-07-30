# Audit de performance de la simulation de portefeuille — Phase 6.6

## Portée et environnement

Mesure effectuée le 30 juillet 2026 sous Windows, Python 3.11.5, dans le
virtualenv du projet. Le script
`backend/scripts/audit_portfolio_simulation.py` n'utilise ni réseau, ni base
applicative, ni dépendance supplémentaire. Il crée une base temporaire, utilise
WAL et la supprime à la fin.

Les durées sont indicatives pour cette machine. Elles ne constituent pas des
seuils de CI. Les assertions portent sur les limites, les lots, les compteurs,
l'ordre, les extrema, le redémarrage et le nettoyage.

Commande :

```powershell
cd backend
.\venv\Scripts\python.exe scripts\audit_portfolio_simulation.py
```

## Méthode

- Petit et moyen : bougies synthétiques UTC à intervalle d'une minute, prix
  positifs déterministes et transitions `accepted` périodiques. Le moteur pur
  produit réellement ordres, exécutions, trades et equity.
- Grand : 500 000 points d'equity constants construits directement pour isoler
  la persistance, la lecture, l'échantillonnage et l'export. Ce cas ne prétend
  pas être un replay de 500 000 bougies.
- Écriture et lecture : lots de 1 000.
- Page brute : au plus 1 000 objets.
- Échantillon : au plus 1 000 objets, premier et dernier conservés.
- Export : consommation fragment par fragment, sans fichier permanent.
- Interruption : arrêt après l'en-tête et le premier lot, fermeture explicite
  du générateur, puis requête de contrôle.
- Redémarrage : nouvelle instance `Database`/`PortfolioRepository` sur le même
  fichier avant suppression.

## Résultats

| Mesure | Petit | Moyen | Grand |
|---|---:|---:|---:|
| Bougies moteur | 300 | 10 000 | non applicable |
| Points equity | 300 | 10 000 | 500 000 |
| Trades | 75 | 2 500 | 0 |
| Ordres / exécutions | 151 / 150 | 5 001 / 5 000 | 1 / 0 |
| Lots d'écriture | 4 | 24 | 501 |
| Simulation | 0,058 s | 14,597 s | non mesurée |
| Génération synthétique | incluse | incluse | 12,719 s |
| Persistance | 0,017 s | 0,280 s | 13,910 s |
| Page brute | 0,005 s / 177 points | 0,050 s / 1 000 | 0,087 s / 1 000 |
| Échantillonnage | 0,009 s / 300 | 0,064 s / 1 000 | 3,686 s / 1 000 |
| Export complet | 0,011 s | 0,273 s | 41,462 s |
| Fragments export | 2 | 11 | 501 |
| Lignes CSV, en-tête inclus | 301 | 10 001 | 500 001 |
| Taille CSV calculée | 62 192 o | 2 122 735 o | 35 389 029 o |
| Taille SQLite avant suppression | 466 944 o | 6 987 776 o | 91 447 296 o |
| Pic `tracemalloc` indicatif | 500 646 o | 16 715 629 o | 85 570 773 o |

La taille SQLite du cas grand est celle du fichier réutilisé successivement par
les trois cas. SQLite réutilise les pages libérées; aucune promesse de réduction
du fichier n'est faite sans `VACUUM`.

## Pagination, échantillonnage et mémoire

- Les pages ne dépassent jamais la limite demandée.
- Le cas moyen et le cas grand retournent exactement 1 000 points pour une page
  brute de limite 1 000.
- L'échantillon grand retourne 1 000 points, dans l'ordre, sans séquence
  inventée. Les tests dédiés verrouillent aussi le maximum global d'equity et le
  maximum global de drawdown.
- Le balayage d'échantillonnage utilise `fetchmany(1000)` et ne construit les
  modèles publics que pour les séquences retenues.
- Le pic grand est faible par rapport à une reconstruction Pydantic complète,
  mais reste indicatif : `tracemalloc` ne mesure pas toutes les allocations
  natives et les décimaux constants sont partagés dans ce dataset.
- Le moteur reste O(n) en mémoire parce qu'il retourne une courbe complète. La
  persistance libère ensuite `BacktestJob.portfolio_result`.

## Export et interruption

L'export grand a produit 501 fragments : un en-tête, puis 500 lots de 1 000.
La première et la dernière séquence étaient respectivement 0 et 499 999. Aucun
`NaN` ou `Infinity` n'a été produit; les lignes sont UTF-8 et CRLF.

L'interruption après le premier lot a fermé le générateur. Une page SQLite a été
lue immédiatement après avec le total exact, sans transaction d'écriture ni
corruption.

## WAL, redémarrage et suppression

`PRAGMA journal_mode` a renvoyé `wal`. La taille WAL observée après les
opérations et la fermeture des connexions courtes était de 0 octet pour les
trois tailles; aucun checkpoint manuel n'a été nécessaire. Ce résultat
n'exclut pas un WAL transitoire pendant une transaction.

Une nouvelle instance de repository a retrouvé les compteurs et le premier
point exactement. La suppression du job a supprimé le run et toutes les lignes
filles par cascade. Elle n'a exécuté ni `VACUUM`, ni politique TTL.

## Risques et recommandations

1. L'export complet de 500 000 points prend nettement plus longtemps que les
   pages et l'échantillonnage; conserver le streaming et informer
   l'utilisateur.
2. Une courbe moteur de 500 000 objets reste le principal risque mémoire avant
   persistance. Une évolution incrémentale serait une Phase ultérieure, pas une
   correction démontrée ici.
3. Surveiller opérationnellement la taille du fichier et supprimer
   explicitement les anciens jobs; ne pas ajouter de TTL implicite.
4. Ne pas introduire de seuil temporel CI dépendant de la machine.

