"""Alias CLI du mode de synchronisation incrémentale."""

from __future__ import annotations

import sys

from app.cli.backfill_candles import main

if __name__ == "__main__":
    raise SystemExit(main(["--mode", "sync", *sys.argv[1:]]))
