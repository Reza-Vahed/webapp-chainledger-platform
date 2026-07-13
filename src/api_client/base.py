"""Abstraktes Interface für Blockchain-Datenquellen.

Kapselt den Zugriff auf eine konkrete Block-Explorer-API, damit die
Datenquelle (aktuell Etherscan) später austauschbar bleibt, ohne dass
Normalisierung, Klassifikation oder CLI angepasst werden müssen.

Sicherheits-Invariante: Implementierungen sind strikt read-only. Sie
dürfen niemals private Keys, Seed-Phrasen oder Zugangsdaten entgegennehmen
und niemals Transaktionen signieren oder senden.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Literal

# Die drei im MVP-Scope enthaltenen Rohdaten-Kategorien.
# Bewusst NICHT enthalten: NFT-Transfers (ERC-721/1155) - außerhalb MVP-Scope.
TransactionCategory = Literal["normal", "internal", "erc20"]

# Callback, der für jede rohe API-Antwortseite aufgerufen wird, BEVOR
# die Daten weiterverarbeitet werden. Dient der unveränderten Ablage
# unter data/raw/ (Auditierbarkeit) - wird vom CLI/Orchestrator injiziert,
# damit der Client selbst keine Kenntnis vom Dateisystem-Layout braucht.
RawResponseSink = Callable[[TransactionCategory, str, int, dict[str, Any]], None]


class BlockchainDataSource(ABC):
    """Abstraktes Interface für read-only On-Chain-Transaktionsabfragen."""

    @abstractmethod
    def fetch_transactions(
        self,
        address: str,
        category: TransactionCategory,
        raw_response_sink: RawResponseSink | None = None,
    ) -> list[dict[str, Any]]:
        """Liefert alle rohen Transaktionen einer Kategorie für eine Adresse.

        Args:
            address: Öffentliche Ethereum-Adresse (0x...).
            category: "normal" | "internal" | "erc20".
            raw_response_sink: Optionaler Callback zur unveränderten
                Persistierung jeder rohen API-Antwortseite.

        Returns:
            Liste roher Transaktions-Dicts im API-nativen Format
            (noch NICHT normalisiert).
        """
        raise NotImplementedError
