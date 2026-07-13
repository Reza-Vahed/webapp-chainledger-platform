"""Export der validierten/klassifizierten Transaktionen als CSV (manueller
Review durch Steuerberater) und JSON (maschinenlesbares Audit-Artefakt) -
parallel, siehe ADR 0003 (Ausgabeformat Option C).

Beträge werden bewusst als String exportiert (nicht als Zahl/Float), um
Rundungsfehler bei steuerlich relevanten Werten zu vermeiden - siehe ADR.
Formatierung erzwingt Festkommadarstellung (kein "1E-18"), da Decimal's
str()-Repräsentation bei sehr kleinen Beträgen (z. B. 1 Wei = 1e-18 ETH)
sonst in wissenschaftliche Notation wechselt.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from src.models import CanonicalTransaction

logger = logging.getLogger(__name__)


def _format_decimal(value: Any) -> str:
    """Formatiert ein Decimal als Festkommazahl (kein '1E-18')."""
    return format(value, "f")

CSV_COLUMNS = [
    "wallet_address",
    "tx_hash",
    "timestamp",
    "category",
    "direction",
    "amount",
    "token_symbol",
    "token_contract_address",
    "from_address",
    "to_address",
    "gas_fee_eth",
    "confidence",
    "warnings",
    "source",
    "record_type",
    "block_number",
    "is_error",
]


def export_transactions(
    transactions: list[CanonicalTransaction],
    output_dir: Path,
    run_id: str,
) -> tuple[Path, Path]:
    """Schreibt dieselben Daten als CSV und JSON nach output_dir.

    run_id wird Teil des Dateinamens, damit frühere Läufe nicht
    stillschweigend überschrieben werden (Auditierbarkeit).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    sorted_txs = sorted(transactions, key=lambda t: (t.wallet_address.lower(), t.timestamp))

    csv_path = output_dir / f"transactions_{run_id}.csv"
    json_path = output_dir / f"transactions_{run_id}.json"

    _write_csv(sorted_txs, csv_path)
    _write_json(sorted_txs, json_path)

    logger.info(
        "Export abgeschlossen: %s Transaktionen -> %s, %s", len(sorted_txs), csv_path, json_path
    )
    return csv_path, json_path


def _write_csv(transactions: list[CanonicalTransaction], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for tx in transactions:
            writer.writerow(_to_csv_row(tx))


def _write_json(transactions: list[CanonicalTransaction], path: Path) -> None:
    payload = [transaction_to_dict(tx) for tx in transactions]
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _to_csv_row(tx: CanonicalTransaction) -> dict[str, Any]:
    return {
        "wallet_address": tx.wallet_address,
        "tx_hash": tx.tx_hash,
        "timestamp": tx.timestamp.isoformat(),
        "category": tx.category.value,
        "direction": tx.direction,
        "amount": _format_decimal(tx.amount),
        "token_symbol": tx.token_symbol,
        "token_contract_address": tx.token_contract_address or "",
        "from_address": tx.from_address,
        "to_address": tx.to_address or "",
        "gas_fee_eth": _format_decimal(tx.gas_fee_eth) if tx.gas_fee_eth is not None else "",
        "confidence": tx.confidence,
        "warnings": "; ".join(tx.warnings),
        "source": tx.source,
        "record_type": tx.record_type.value,
        "block_number": tx.block_number,
        "is_error": tx.is_error,
    }


def transaction_to_dict(tx: CanonicalTransaction) -> dict[str, Any]:
    """Öffentliche JSON-Serialisierung einer kanonischen Transaktion -
    von _write_json UND vom Web-Backend (api/routers/imports.py) genutzt,
    damit die Formatierung (insb. Decimal-Festkommadarstellung) nicht an
    zwei Stellen gepflegt werden muss."""
    return {
        "wallet_address": tx.wallet_address,
        "tx_hash": tx.tx_hash,
        "timestamp": tx.timestamp.isoformat(),
        "category": tx.category.value,
        "direction": tx.direction,
        "amount": _format_decimal(tx.amount),
        "token_symbol": tx.token_symbol,
        "token_contract_address": tx.token_contract_address,
        "from_address": tx.from_address,
        "to_address": tx.to_address,
        "gas_fee_eth": _format_decimal(tx.gas_fee_eth) if tx.gas_fee_eth is not None else None,
        "confidence": tx.confidence,
        "warnings": tx.warnings,
        "source": tx.source,
        "record_type": tx.record_type.value,
        "block_number": tx.block_number,
        "is_error": tx.is_error,
    }
