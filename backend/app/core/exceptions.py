"""Exceptions métier explicites du backend de scan."""


class ScannerError(Exception):
    """Classe de base des erreurs de scan attendues et présentables à l'API."""


class UnknownExchangeError(ScannerError):
    """Signale qu'un identifiant ne correspond à aucune classe CCXT.

    Cette erreur naît dans l'adaptateur d'exchange. Elle n'est pas récupérable
    sans corriger ``exchange_id`` et remonte actuellement comme erreur serveur.
    """


class CandleStorageError(ScannerError):
    """Signale que la base locale ne peut pas satisfaire une opération."""


class InsufficientHistoryError(ScannerError):
    """Signale qu'un exchange ne fournit pas l'historique minimal demandé."""


class UnsupportedTimeframeError(ScannerError):
    """Signale un timeframe absent du contrat OHLCV."""


class UnknownSymbolError(ScannerError):
    """Signale un symbole absent des marchés chargés par l'exchange."""


class PaginationStalledError(ScannerError):
    """Signale une pagination CCXT dont le dernier timestamp ne progresse plus."""


class InvalidOhlcvError(ScannerError):
    """Signale une réponse OHLCV inutilisable."""


class CandleLimitError(ScannerError):
    """Signale une limite de lecture supérieure à la borne locale."""


class InvalidTimeRangeError(ScannerError):
    """Signale une plage où la borne de fin ne suit pas la borne de début."""


class BackfillError(ScannerError):
    """Classe de base des erreurs attendues du backfill historique."""


class BackfillPaginationError(BackfillError):
    """Signale une page historique incohérente ou immobile."""


class BacktestCoverageError(ScannerError):
    """Signale une couverture locale insuffisante pour un futur backtest."""
