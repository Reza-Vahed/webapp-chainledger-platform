"""Zentrale Logging-Konfiguration (Standard-Logging, kein Framework).

Erfüllt Anforderung: API-Aufrufe, Fehler, Rate-Limit-Ereignisse und
unklassifizierte Transaktionen müssen nachvollziehbar geloggt werden.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(log_file: Path | None = None, level: int = logging.INFO) -> None:
    """Konfiguriert das Root-Logging einmalig für die gesamte Anwendung.

    Schreibt immer nach stderr (sichtbar im CLI-Betrieb) und optional
    zusätzlich in eine Log-Datei für die spätere Nachvollziehbarkeit.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=level, format=LOG_FORMAT, handlers=handlers, force=True)
