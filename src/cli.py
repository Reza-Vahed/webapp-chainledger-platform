"""CLI-Einstiegspunkt: Datenimport-Agent für Ethereum-Wallet-Adressen.

Orchestriert die gesamte Pipeline:
  Abruf (EtherscanClient) -> Rohdaten-Persistenz (data/raw/, unveraendert)
  -> Normalisierung -> Klassifikation -> Validierung
  -> Export (data/processed/, CSV + JSON)

Strikt read-only: akzeptiert ausschließlich öffentliche Wallet-Adressen als
Input. Es gibt keinen Code-Pfad für private Keys, Seed-Phrasen oder das
Signieren/Senden von Transaktionen.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.api_client.etherscan_client import EtherscanClient
from src.api_client.exceptions import EtherscanAPIError
from src.classifier import classify_transactions
from src.exporter import export_transactions
from src.logging_config import configure_logging
from src.models import CanonicalTransaction, SourceRecordType, TxCategory
from src.normalizer import normalize_transactions
from src.validator import validate_transactions

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_LOG_DIR = PROJECT_ROOT / "data" / "logs"

CATEGORIES: tuple[SourceRecordType, ...] = (
    SourceRecordType.NORMAL,
    SourceRecordType.INTERNAL,
    SourceRecordType.ERC20,
)

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


def make_raw_sink(raw_dir: Path, run_id: str) -> Callable[[str, str, int, dict[str, Any]], None]:
    """Baut den Callback, der jede rohe API-Antwortseite unveraendert unter
    data/raw/ ablegt (Anforderung: Auditierbarkeit). Der Client selbst hat
    keine Kenntnis vom Dateisystem-Layout - siehe api_client/base.py."""
    raw_dir.mkdir(parents=True, exist_ok=True)

    def sink(category: str, address: str, page: int, data: dict[str, Any]) -> None:
        filename = f"{run_id}_{address.lower()}_{category}_page{page:04d}.json"
        path = raw_dir / filename
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("Rohantwort gespeichert: %s", path)

    return sink


ProgressCallback = Callable[[dict[str, Any]], None]


def run_import(
    addresses: list[str],
    client: EtherscanClient,
    raw_dir: Path,
    processed_dir: Path,
    run_id: str,
    progress_callback: ProgressCallback | None = None,
) -> tuple[Path, Path, list[CanonicalTransaction]]:
    """Führt die volle Pipeline für eine oder mehrere Wallets aus und
    liefert die Pfade zu CSV/JSON sowie die validierten Transaktionen.

    progress_callback ist optional und rein additiv (Default None, CLI-
    Verhalten unveraendert) - wird u. a. vom Web-Backend (api/jobs.py)
    genutzt, um Live-Fortschritt fuer Polling bereitzustellen, ohne die
    Pipeline-Module selbst anzufassen.
    """

    def report(event: str, **kwargs: Any) -> None:
        if progress_callback is not None:
            progress_callback({"event": event, **kwargs})

    raw_sink = make_raw_sink(raw_dir, run_id)
    all_normalized: list[CanonicalTransaction] = []

    for address in addresses:
        if not ADDRESS_PATTERN.match(address):
            logger.error("Ungültiges Adressformat, überspringe: %s", address)
            report("address_invalid", address=address)
            continue

        logger.info("Starte Import für Wallet %s", address)
        report("address_start", address=address)
        for category in CATEGORIES:
            report("category_start", address=address, category=category.value)

            def sink_with_progress(
                cat: str, addr: str, page: int, data: dict[str, Any], _raw_sink: Callable = raw_sink
            ) -> None:
                _raw_sink(cat, addr, page, data)
                result = data.get("result")
                page_count = len(result) if isinstance(result, list) else 0
                report("category_page", address=addr, category=cat, page=page, page_count=page_count)

            try:
                raw_txs = client.fetch_transactions(address, category.value, raw_response_sink=sink_with_progress)
            except EtherscanAPIError as exc:
                logger.error(
                    "Abruf fehlgeschlagen (address=%s category=%s): %s", address, category.value, exc
                )
                report("category_error", address=address, category=category.value, error=str(exc))
                continue
            normalized = normalize_transactions(raw_txs, category, address)
            logger.info(
                "Normalisiert: address=%s category=%s anzahl=%s", address, category.value, len(normalized)
            )
            report("category_done", address=address, category=category.value, count=len(normalized))
            all_normalized.extend(normalized)

    report("stage", stage="classifying")
    classified = classify_transactions(all_normalized)

    report("stage", stage="validating")
    validated = validate_transactions(classified)

    unclassified = [tx for tx in validated if tx.category == TxCategory.UNCLASSIFIED]
    if unclassified:
        logger.info(
            "%s von %s Transaktionen unklassifiziert - manuelle Pruefung empfohlen (siehe warnings-Spalte)",
            len(unclassified), len(validated),
        )

    report("stage", stage="exporting")
    csv_path, json_path = export_transactions(validated, processed_dir, run_id)

    report("done", total=len(validated), csv_path=str(csv_path), json_path=str(json_path))
    return csv_path, json_path, validated


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    configure_logging(log_file=args.log_dir / f"run_{run_id}.log")

    try:
        client = EtherscanClient.from_env(env_file=args.env_file)
    except ValueError as exc:
        logger.error("Konfigurationsfehler: %s", exc)
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    csv_path, json_path, validated = run_import(
        addresses=args.addresses,
        client=client,
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        run_id=run_id,
    )

    print(f"Import abgeschlossen: {len(validated)} Transaktionen verarbeitet.")
    print(f"  CSV:  {csv_path}")
    print(f"  JSON: {json_path}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Krypto-Steuer-Datenimport-Agent (Ethereum Mainnet, read-only, MVP)."
    )
    parser.add_argument("addresses", nargs="+", help="Eine oder mehrere Ethereum-Wallet-Adressen (0x...)")
    parser.add_argument(
        "--env-file", type=Path, default=None,
        help="Pfad zu einer .env-Datei (Default: .env im Projektverzeichnis / Umgebungsvariablen)",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
