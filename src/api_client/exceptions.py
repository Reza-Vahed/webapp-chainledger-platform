"""Fehlerklassen für den API-Client. Bewusst schlank gehalten (MVP)."""

from __future__ import annotations


class EtherscanAPIError(Exception):
    """Etherscan hat einen fachlichen Fehler zurückgegeben (status != Erfolg,
    aber kein Rate-Limit-Fall - z. B. ungültiger API-Key, ungültige Adresse)."""


class RateLimitExceededError(EtherscanAPIError):
    """Rate-Limit wurde auch nach allen Retry-Versuchen nicht respektiert
    bzw. der Aufruf ist wiederholt an einem Netzwerkfehler gescheitert."""
