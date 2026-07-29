# Jobs, progression et annulation

## Stockage et création

`ScanManager` conserve dans des dictionnaires en mémoire les `ScanJob`, tâches `asyncio`, conditions et versions de publication. Un identifiant `uuid4().hex` est créé, le job est enregistré en `pending`, puis `_run_job()` est planifié.

La tâche passe le job à `running`, fixe `started_at`, instancie `ScannerService` et publie chaque progression. La terminaison fixe toujours `completed_at` et publie un dernier snapshot.

## Progression et publication

Le premier callback fixe `total` après filtrage des marchés. Après chaque analyse :

- `processed` augmente de 1 ;
- un seul de `successful`, `filtered` ou `errors` augmente ;
- le callback reçoit une copie profonde ;
- le manager incrémente la version et réveille les abonnés de l'`asyncio.Condition`.

Le WebSocket n'effectue donc aucun polling. Plusieurs abonnés peuvent attendre la même condition. Le calcul de `percent` est effectué lors de la sérialisation publique.

## Concurrence et isolation

Le scanner maintient au plus `max_concurrency` tâches planifiées et utilise aussi un sémaphore de même capacité. Quand un lot de tâches se termine, un nouveau symbole est planifié par tâche achevée. Il n'existe pas de pool persistant au-delà du scan.

`_analyze_guarded()` laisse remonter `CancelledError`, mais transforme toute autre exception de symbole en `AnalysisOutcome(ERROR)`. Le scan global continue et incrémente `errors`.

## Annulation et résultats partiels

`DELETE` annule une tâche encore active et attend son arrêt. `ScannerService.scan()` annule ses analyses restantes, les rassemble avec `return_exceptions=true`, puis ferme l'exchange. Le manager copie `partial_results`, passe le job à `cancelled` et fixe sa date de fin.

Un job annulé autorise `/results` et `/export.csv`. Les résultats sont partiels et peuvent ne pas être triés si l'annulation intervient avant le tri final. Annuler un job déjà final ne change pas son état.

Une annulation extrêmement précoce, avant l'entrée dans `_run_job`, est aussi traduite en `cancelled` par `cancel_job()`.

## Échec

Une exception globale hors annulation passe le job à `failed`, renseigne `error` et écrit une trace. Les endpoints de résultats et CSV répondent 409 pour cet état. Les erreurs ordinaires d'une paire ne produisent pas `failed`.

## Rétention et nettoyage

La purge a lieu uniquement lors de `create_job()`, sous verrou. Elle supprime :

- les jobs terminés avant `now - JOB_TTL_SECONDS` ;
- les plus anciens jobs terminés nécessaires pour laisser de la place à la nouvelle création selon `MAX_RETAINED_JOBS`.

Les références de job, tâche, condition et version sont retirées ensemble. Aucun job actif n'est supprimé. Une tâche terminée reste référencée tant que son job n'est pas purgé ; il n'existe pas de nettoyage périodique autonome.

## Limites du modèle mémoire

- Un redémarrage perd jobs, résultats et exports non téléchargés.
- Tous les WebSockets sont interrompus au redémarrage.
- Plusieurs workers possèdent des registres différents : une requête peut ne pas retrouver le job créé par un autre worker.
- Le TTL n'est pas une garantie d'expiration immédiate, puisque la purge attend la création suivante.
- La capacité peut dépasser momentanément la limite si de nombreux jobs actifs ne peuvent pas être purgés.
