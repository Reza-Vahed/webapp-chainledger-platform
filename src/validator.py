"""Erkennt offensichtliche Fehler/Lücken in kanonischen Transaktionen und
markiert sie mit zusätzlichen Warnhinweisen.

Wichtig: Es wird NICHTS automatisch "repariert" - steuerlich relevante
Werte dürfen nur durch eine menschliche Prüfung verändert werden. Der
Validator fügt ausschließlich Warnhinweise hinzu.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.models import CanonicalTransaction, SourceRecordType

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.5
# Erster Ethereum-Mainnet-Block wurde am 30.07.2015 gemined - alles davor
# ist per Definition ein unplausibler Zeitstempel.
ETHEREUM_GENESIS = datetime(2015, 7, 30, tzinfo=timezone.utc)


def validate_transactions(transactions: list[CanonicalTransaction]) -> list[CanonicalTransaction]:
    """Prüft eine Liste kanonischer Transaktionen auf offensichtliche
    Auffälligkeiten und gibt NEUE Instanzen mit ergänzten Warnhinweisen
    zurück (keine Mutation, keine Wertänderung)."""
    now = datetime.now(timezone.utc)
    fingerprints = [_fingerprint(tx) for tx in transactions]
    fingerprint_counts: dict[str, int] = {}
    for fp in fingerprints:
        fingerprint_counts[fp] = fingerprint_counts.get(fp, 0) + 1

    validated: list[CanonicalTransaction] = []
    for tx, fp in zip(transactions, fingerprints):
        warnings = list(tx.warnings)

        if fingerprint_counts[fp] > 1:
            warnings.append(
                "data_gap_or_error: exaktes Duplikat innerhalb derselben Wallet erkannt - nicht automatisch dedupliziert"
            )

        if tx.is_error and tx.amount > 0:
            warnings.append(
                "data_gap_or_error: fehlgeschlagene Transaktion mit Betrag > 0 - moegliche Dateninkonsistenz"
            )

        if tx.timestamp < ETHEREUM_GENESIS or tx.timestamp > now:
            warnings.append(
                "data_gap_or_error: unplausibler Zeitstempel (vor Ethereum-Genesis oder in der Zukunft)"
            )

        if tx.record_type == SourceRecordType.NORMAL and not tx.is_error and tx.gas_fee_eth is None:
            warnings.append("data_gap_or_error: fehlende Gas-Fee-Daten fuer normale Transaktion")

        if tx.confidence < LOW_CONFIDENCE_THRESHOLD and not any(
            w.startswith("manual_review_required") for w in warnings
        ):
            warnings.append("manual_review_required: niedrige Klassifikations-Konfidenz")

        deduped_warnings = list(dict.fromkeys(warnings))  # Reihenfolge stabil, keine Duplikate

        if len(deduped_warnings) > len(tx.warnings):
            logger.info(
                "Validierung: neue Warnhinweise fuer hash=%s wallet=%s: %s",
                tx.tx_hash, tx.wallet_address, deduped_warnings[len(tx.warnings):],
            )

        validated.append(tx.model_copy(update={"warnings": deduped_warnings}))

    return validated


def _fingerprint(tx: CanonicalTransaction) -> str:
    return "|".join(
        [
            tx.wallet_address.lower(),
            tx.tx_hash,
            tx.record_type.value,
            tx.from_address.lower(),
            (tx.to_address or "").lower(),
            str(tx.amount),
            tx.token_symbol,
        ]
    )
