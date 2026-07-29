# Contrat cohérent des signaux — phase 2

## Disponibilité

Chaque facteur utilise `available`, `insufficient_data`, `invalid_data` ou
`disabled`. Un signal réellement `neutral` reste `available`. Seuls les facteurs
disponibles participent à la confluence ; les poids restants sont renormalisés.
Sans facteur disponible, score et grade sont `null`.

## Snapshots du marché

`snapshot.confirmed` utilise uniquement les bougies clôturées et contient prix,
timestamp, signaux, disponibilités et confluence. `snapshot.provisional` inclut
la bougie ouverte, porte `is_forming: true` et vaut `null` sans bougie ouverte.
Les updates intrabougie ne modifient pas `confirmed`. À la clôture, le provisoire
entre dans la vue confirmée et la nouvelle bougie devient provisoire.

Les anciens champs `snapshot.rsi`, `trend`, `macd`, `bollinger`, `stochastic` et
`confluence` restent dérivés de la vue active pour compatibilité. Le frontend
utilise les nouvelles vues. Leur suppression est réservée à une future version
majeure après vérification des consommateurs.

## Profil d'indicateurs

`MarketIndicatorConfig` contient activations, périodes RSI/SMA/EMA, paramètres
MACD/Bollinger/Stochastique, seuil RSI et poids. Son origine est `default`,
`scan` ou `custom`. Il est sérialisé en JSON dans le paramètre URL `profile`,
transmis aux routes candles et au WebSocket. Une URL ancienne utilise le profil
historique par défaut. Un lien scanner conserve symbole, timeframe et profil.

## Tendance

Une famille est `bullish` si fast > slow et prix > fast, `bearish` si fast < slow
et prix < fast, sinon `neutral`. Sans fast elle est `unavailable`. Avec SMA et
EMA, un état directionnel exige leur accord ; tout désaccord produit `neutral`.

`trend_score` reste le nombre de timeframes bullish et continue d'alimenter
`min_trend_score`. `trend_net_score` utilise +1/0/-1 et `trend_states` expose le
détail. Le facteur de confluence est la moyenne bullish=1, neutral=0.5,
bearish=0, indisponible exclu.

## Confluence explicable

Chaque entrée `details` contient disponibilité, valeur brute, classe, facteur,
poids configuré, poids effectif, contribution et raison. Le score n'est ni une
probabilité ni une garantie. Il reste orienté vers une configuration haussière
après repli et n'a pas été validé par backtest.

## Validation et migration

REST et WebSocket utilisent les mêmes vues. Le frontend valide chaque message
WebSocket avec Zod avant Zustand. Un message invalide rend une erreur visible
sans muter les séries et sans désactiver la reconnexion.

Restent hors phase 2 : règles et seuils de divergences, seuil MACD nul des
divergences, poids par défaut, backtest et passage d'ordres.
