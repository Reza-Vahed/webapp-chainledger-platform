"""Klassifiziert kanonische Transaktionen nach der festen Kategorienliste:
Transfer-In, Transfer-Out, Swap, Staking-Reward, Airdrop,
Contract-Interaktion, Unklassifiziert.

Kernprinzip: Bei On-Chain-Mehrdeutigkeit wird NIE geraten. Insbesondere:
- Kauf/Verkauf-Richtung bei DEX-Swaps wird nicht unterschieden -> "Swap".
- Staking-Rewards und Airdrops werden NUR bei Treffer auf eine explizite,
  dokumentierte Allowlist bekannter Contracts vergeben - sonst
  "Unklassifiziert" (ggf. mit Hinweis zur manuellen Prüfung).

Swap-Erkennung erfordert die Betrachtung aller Records (normal/internal/
erc20) desselben tx_hash, da ein Swap i. d. R. aus mehreren Legs besteht
(z. B. ERC20-Out + ERC20-In, oder ETH-Out + ERC20-In). Deshalb wird zuerst
nach tx_hash gruppiert.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from src.models import CanonicalTransaction, SourceRecordType, TxCategory

logger = logging.getLogger(__name__)

# Keys müssen lowercase sein - der Abgleich normalisiert tx.from_address
# defensiv selbst (nicht auf Lowercasing durch den Normalizer verlassen).
#
# Chain-geschlüsselt (Key = CanonicalTransaction.chain, siehe
# src/api_client/chains.py): Contract-Adressen sind chain-spezifisch,
# eine Mainnet-Adresse darf auf einer anderen Chain nicht zufällig
# denselben Vertrag bedeuten. Bewusst kleine, dokumentierte Allowlist
# bekannter Staking-Contracts pro Chain - fehlt ein Eintrag für eine
# Chain, fällt die Transaktion konsequent auf "Unklassifiziert" zurück
# statt zu raten (siehe KNOWN_AIRDROP_CONTRACTS-Pattern unten).
# Bekannte Einschränkung (MVP): Rebase-/Liquid-Staking-Token wie stETH
# erzeugen Rewards teils über Balance-Rebasing statt klassischer Transfer-
# Events und werden dadurch über die Etherscan-Account-API nicht
# vollständig erfasst - siehe README.
KNOWN_STAKING_CONTRACTS: dict[str, dict[str, str]] = {
    "ethereum": {
        "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "Lido: stETH Token",
        "0xae78736cd615f374d3085123a210448e74fc639": "Rocket Pool: rETH Token",
    },
    # Arbitrum: noch keine recherchierte, verlässliche Allowlist - bewusst
    # leer statt spekulativ befüllt (siehe KNOWN_AIRDROP_CONTRACTS-Prinzip).
    "arbitrum": {},
}

# Bewusst leere Allowlist für bekannte Airdrop-Distributor-Contracts im
# MVP (chain-geschlüsselt wie KNOWN_STAKING_CONTRACTS): Airdrop-Contracts
# sind i. d. R. projektspezifische Einmal-Deployments ohne verlässliche
# generische On-Chain-Signatur. Statt eine unsichere Heuristik zu raten,
# bleibt diese Liste leer/erweiterbar - Treffer landen konsequent in
# "Unklassifiziert".
KNOWN_AIRDROP_CONTRACTS: dict[str, dict[str, str]] = {
    "ethereum": {},
    "arbitrum": {},
}


def classify_transactions(
    transactions: list[CanonicalTransaction],
) -> list[CanonicalTransaction]:
    """Klassifiziert eine Liste kanonischer Transaktionen (eine oder
    mehrere Wallets). Gibt NEUE CanonicalTransaction-Instanzen zurück
    (Pydantic-Modelle sind hier bewusst nicht mutiert)."""
    groups: dict[tuple[str, str], list[CanonicalTransaction]] = defaultdict(list)
    for tx in transactions:
        groups[(tx.wallet_address.lower(), tx.tx_hash)].append(tx)

    classified: list[CanonicalTransaction] = []
    for group in groups.values():
        classified.extend(_classify_group(group))

    return classified


def _classify_group(group: list[CanonicalTransaction]) -> list[CanonicalTransaction]:
    has_erc20_in = any(t.record_type == SourceRecordType.ERC20 and t.direction == "in" for t in group)
    has_erc20_out = any(t.record_type == SourceRecordType.ERC20 and t.direction == "out" for t in group)
    has_eth_value_in = any(
        t.direction == "in" and t.amount > 0 and t.record_type in (SourceRecordType.NORMAL, SourceRecordType.INTERNAL)
        for t in group
    )
    has_eth_value_out = any(
        t.direction == "out" and t.amount > 0 and t.record_type == SourceRecordType.NORMAL
        for t in group
    )

    is_swap_pattern = (
        (has_erc20_in and has_erc20_out)
        or (has_erc20_in and has_eth_value_out)
        or (has_erc20_out and has_eth_value_in)
    )

    return [_classify_single(tx, is_swap_pattern) for tx in group]


def _classify_single(tx: CanonicalTransaction, is_swap_pattern: bool) -> CanonicalTransaction:
    category: TxCategory
    confidence: float
    extra_warnings: list[str] = []

    if tx.is_error:
        category, confidence = TxCategory.UNCLASSIFIED, 0.0
        extra_warnings.append(
            "manual_review_required: fehlgeschlagene On-Chain-Ausführung, i. d. R. nicht steuerrelevant - bitte prüfen"
        )
    elif is_swap_pattern:
        category, confidence = TxCategory.SWAP, 0.7
        extra_warnings.append(
            "info: Swap-Muster (mehrere Legs im selben tx_hash) erkannt, Kauf/Verkauf-Zuordnung nicht ermittelt"
        )
    elif tx.direction == "in" and tx.from_address.lower() in KNOWN_STAKING_CONTRACTS.get(tx.chain, {}):
        category, confidence = TxCategory.STAKING_REWARD, 0.9
    elif (
        tx.record_type == SourceRecordType.ERC20
        and tx.direction == "in"
        and tx.from_address.lower() in KNOWN_AIRDROP_CONTRACTS.get(tx.chain, {})
    ):
        category, confidence = TxCategory.AIRDROP, 0.9
    elif tx.record_type == SourceRecordType.NORMAL and not _is_empty_input(tx.input_data) and tx.amount == 0:
        # Reiner Funktionsaufruf ohne Wertübertragung (z. B. Approve,
        # Claim ohne erkannten Reward-Leg, Contract-Setup etc.)
        category, confidence = TxCategory.CONTRACT_INTERACTION, 0.6
    elif tx.record_type in (SourceRecordType.NORMAL, SourceRecordType.ERC20):
        if tx.record_type == SourceRecordType.NORMAL and not _is_empty_input(tx.input_data):
            # Normale Tx mit Value UND Input-Daten außerhalb eines
            # erkannten Swap-Musters: Zweck nicht eindeutig bestimmbar.
            category, confidence = TxCategory.UNCLASSIFIED, 0.3
            extra_warnings.append(
                "manual_review_required: Contract-Aufruf mit Wertübertragung außerhalb erkannter Muster"
            )
        else:
            category = TxCategory.TRANSFER_IN if tx.direction == "in" else TxCategory.TRANSFER_OUT
            confidence = 0.9
    elif tx.record_type == SourceRecordType.INTERNAL:
        category = TxCategory.TRANSFER_IN if tx.direction == "in" else TxCategory.TRANSFER_OUT
        confidence = 0.6
        extra_warnings.append(
            "manual_review_required: interner Transfer, auslösender Kontext nicht abschließend prüfbar"
        )
    else:
        category, confidence = TxCategory.UNCLASSIFIED, 0.0
        extra_warnings.append("manual_review_required: kein eindeutiges Muster erkannt")

    if category == TxCategory.UNCLASSIFIED:
        logger.info(
            "Unklassifizierte Transaktion: hash=%s wallet=%s record_type=%s",
            tx.tx_hash, tx.wallet_address, tx.record_type.value,
        )

    return tx.model_copy(
        update={
            "category": category,
            "confidence": confidence,
            "warnings": [*tx.warnings, *extra_warnings],
        }
    )


def _is_empty_input(input_data: str | None) -> bool:
    return input_data is None or input_data.lower() in ("", "0x")
