"""API-unabhängiges, kanonisches Transaktionsmodell (Pydantic).

Dies ist die zentrale Datenstruktur der Pipeline: Normalizer erzeugen sie
aus Rohdaten, der Classifier reichert sie an, Validator/Exporter arbeiten
ausschließlich auf ihr. Kein Modul außer dem Normalizer kennt das
API-native Rohformat.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceRecordType(str, Enum):
    """Herkunftskategorie der Rohdaten (API-seitig). Entspricht den drei
    im MVP abgedeckten Etherscan-Endpunkten - NICHT zu verwechseln mit der
    steuerlich relevanten Klassifikation (siehe TxCategory)."""

    NORMAL = "normal"
    INTERNAL = "internal"
    ERC20 = "erc20"


class TxCategory(str, Enum):
    """Feste Klassifikations-Kategorienliste (siehe Aufgabenstellung).
    Absichtlich abschließend - keine freien/erratenen Werte."""

    TRANSFER_IN = "Transfer-In"
    TRANSFER_OUT = "Transfer-Out"
    SWAP = "Swap"
    STAKING_REWARD = "Staking-Reward"
    AIRDROP = "Airdrop"
    CONTRACT_INTERACTION = "Contract-Interaktion"
    UNCLASSIFIED = "Unklassifiziert"


class CanonicalTransaction(BaseModel):
    """Eine normalisierte On-Chain-Transaktion aus Sicht EINER Wallet.

    Bei Interaktion zwischen zwei selbst importierten Wallets entsteht
    bewusst je ein Record pro Wallet (kein Cross-Wallet-Netting) - jede
    Zeile muss für sich genommen prüfbar bleiben.
    """

    model_config = ConfigDict(use_enum_values=False)

    # Herkunft / Identität
    wallet_address: str
    tx_hash: str
    record_type: SourceRecordType
    source: str = "etherscan"

    # Zeit- und Block-Kontext
    timestamp: datetime
    block_number: int

    # Bewegungsdaten
    from_address: str
    to_address: Optional[str] = None
    direction: Literal["in", "out"]
    amount: Decimal
    token_symbol: str
    token_contract_address: Optional[str] = None
    token_decimals: int = 18

    # Nur für record_type == NORMAL relevant (Gebühren-/Kontext-Info)
    gas_fee_eth: Optional[Decimal] = None
    input_data: Optional[str] = None
    is_error: bool = False

    # Vom Classifier befüllt (Default = unklassifiziert, nicht geraten)
    category: TxCategory = TxCategory.UNCLASSIFIED
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    warnings: list[str] = Field(default_factory=list)
