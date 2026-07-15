"""Job-Verwaltung für asynchrone Import-Läufe.

Führt die bestehende Pipeline (src.cli.run_import) in einem Hintergrund-
Thread aus, damit der FastAPI-Event-Loop für Status-Polling frei bleibt -
ohne den (synchronen) API-Client/die Pipeline umzuschreiben.

Laufende Jobs leben weiterhin primär im Prozess-Speicher (_jobs) - das
hält das häufige Status-Polling (alle 1.5s) schnell und lock-nah wie
bisher. Bei jedem Statusübergang wird zusätzlich ein Snapshot der
Metadaten nach SQLite geschrieben (api/db.py, Write-Through), damit
abgeschlossene Importe einen Neustart überstehen. Die Transaktionsdaten
selbst werden NICHT dupliziert - sie liegen bereits vollständig in
data/processed/transactions_<job_id>.json (siehe src/exporter.py) und
werden bei Bedarf nach einem Neustart von dort zurückgelesen (siehe
_load_job_from_store). Bekannte MVP-Grenze: kein Multi-Worker-Support
(ein Prozess hält die laufenden Jobs im Speicher) und ein Job, der beim
Absturz/Neustart des Backends gerade "running" war, bleibt in der
Historie dauerhaft auf "running" stehen (keine Recovery-Heuristik) -
siehe README.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from api import db
from src.api_client.chains import DEFAULT_CHAIN_KEY, get_chain
from src.api_client.etherscan_client import EtherscanClient
from src.cli import CATEGORIES, run_import
from src.models import CanonicalTransaction, TxCategory

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SORTABLE_FIELDS: dict[str, Callable[[CanonicalTransaction], Any]] = {
    "timestamp": lambda t: t.timestamp,
    "amount": lambda t: t.amount,
    "confidence": lambda t: t.confidence,
    "category": lambda t: t.category.value,
    "block_number": lambda t: t.block_number,
}
DEFAULT_SORT = "timestamp"
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_DB_PATH = db.DEFAULT_DB_PATH


@dataclass
class CategoryProgress:
    status: str = "pending"
    pages_fetched: int = 0
    records_fetched: int = 0
    error: str | None = None


@dataclass
class AddressProgress:
    categories: dict[str, CategoryProgress] = field(default_factory=dict)


@dataclass
class Job:
    id: str
    addresses: list[str]
    chain: str = DEFAULT_CHAIN_KEY
    state: str = "queued"  # queued | running | done | error
    stage: str | None = None  # fetching | classifying | validating | exporting
    address_progress: dict[str, AddressProgress] = field(default_factory=dict)
    total_transactions: int | None = None
    unclassified_count: int | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    csv_path: Path | None = None
    json_path: Path | None = None
    transactions: list[CanonicalTransaction] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def create_job(addresses: list[str], client: EtherscanClient, chain: str = DEFAULT_CHAIN_KEY) -> str:
    """Legt einen neuen Job an und startet ihn sofort in einem
    Hintergrund-Thread. Gibt die job_id zurück, ohne auf den Abschluss zu
    warten (Fortschritt wird über get_job()/to_status_response() gepollt)."""
    job_id = str(uuid.uuid4())
    job = Job(id=job_id, addresses=list(addresses), chain=chain)
    for address in addresses:
        job.address_progress[address] = AddressProgress(
            categories={c.value: CategoryProgress() for c in CATEGORIES}
        )
    with _jobs_lock:
        _jobs[job_id] = job
    _persist(job)

    thread = threading.Thread(target=_execute_job, args=(job, client), daemon=True)
    thread.start()
    return job_id


def get_job(job_id: str) -> Job | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is not None:
        return job
    return _load_job_from_store(job_id)


def delete_job(job_id: str) -> bool:
    """Löscht Metadaten (DB) sowie die zugehörigen Roh-/Export-Dateien
    eines Jobs. Gibt True zurück, wenn der Job existierte. Läuft ein Job
    gerade (queued/running), muss der Aufrufer das vorher separat prüfen -
    diese Funktion entfernt bedingungslos, was sie findet."""
    with _jobs_lock:
        in_memory_job = _jobs.pop(job_id, None)
    existed_in_db = db.delete_job(job_id, db_path=DEFAULT_DB_PATH)

    for path in DEFAULT_PROCESSED_DIR.glob(f"transactions_{job_id}.*"):
        path.unlink(missing_ok=True)
    for path in DEFAULT_RAW_DIR.glob(f"{job_id}_*.json"):
        path.unlink(missing_ok=True)

    return in_memory_job is not None or existed_in_db


def list_job_summaries() -> list[dict[str, Any]]:
    """Liste aller bekannten Jobs (jede Chain, jeder Status) für die
    Import-Historie, neueste zuerst - direkt aus der DB, nicht aus dem
    In-Memory-Cache (damit auch nach einem Neustart vollständig)."""
    rows = db.list_jobs(db_path=DEFAULT_DB_PATH)
    return [
        {
            "job_id": row["id"],
            "chain": row["chain"],
            "addresses": row["addresses"],
            "state": row["state"],
            "error": row["error"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "total_transactions": row["total_transactions"],
            "unclassified_count": row["unclassified_count"],
            "csv_available": bool(row["csv_path"]),
            "json_available": bool(row["json_path"]),
        }
        for row in rows
    ]


def _job_meta(job: Job) -> dict[str, Any]:
    with job.lock:
        return {
            "id": job.id,
            "chain": job.chain,
            "addresses": list(job.addresses),
            "state": job.state,
            "error": job.error,
            "started_at": job.started_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "total_transactions": job.total_transactions,
            "unclassified_count": job.unclassified_count,
            "csv_path": str(job.csv_path) if job.csv_path else None,
            "json_path": str(job.json_path) if job.json_path else None,
        }


def _persist(job: Job) -> None:
    db.upsert_job(_job_meta(job), db_path=DEFAULT_DB_PATH)


def _load_job_from_store(job_id: str) -> Job | None:
    """Rekonstruiert einen Job aus der DB (Metadaten) + ggf. der bereits
    vorhandenen JSON-Export-Datei (Transaktionen), wenn er nicht (mehr) im
    In-Memory-Cache liegt - typischerweise nach einem Backend-Neustart.
    Der pro-Kategorie-Fortschritt (address_progress) ist bewusst NICHT
    persistiert (rein während des Laufs relevant) und bleibt nach
    Rekonstruktion leer."""
    meta = db.get_job(job_id, db_path=DEFAULT_DB_PATH)
    if meta is None:
        return None

    csv_path = Path(meta["csv_path"]) if meta["csv_path"] else None
    json_path = Path(meta["json_path"]) if meta["json_path"] else None

    job = Job(
        id=meta["id"],
        addresses=meta["addresses"],
        chain=meta["chain"],
        state=meta["state"],
        error=meta["error"],
        started_at=datetime.fromisoformat(meta["started_at"]),
        finished_at=datetime.fromisoformat(meta["finished_at"]) if meta["finished_at"] else None,
        total_transactions=meta["total_transactions"],
        unclassified_count=meta["unclassified_count"],
        csv_path=csv_path,
        json_path=json_path,
    )
    if job.state == "done" and json_path is not None and json_path.exists():
        job.transactions = _load_transactions_from_json(json_path)

    with _jobs_lock:
        _jobs.setdefault(job_id, job)
        return _jobs[job_id]


def _load_transactions_from_json(json_path: Path) -> list[CanonicalTransaction]:
    with json_path.open(encoding="utf-8") as f:
        raw_entries = json.load(f)
    return [CanonicalTransaction.model_validate(entry) for entry in raw_entries]


def _execute_job(job: Job, client: EtherscanClient) -> None:
    with job.lock:
        job.state = "running"
        job.stage = "fetching"
    _persist(job)

    def on_progress(event: dict[str, Any]) -> None:
        _handle_progress_event(job, event)

    try:
        csv_path, json_path, validated = run_import(
            addresses=job.addresses,
            client=client,
            raw_dir=DEFAULT_RAW_DIR,
            processed_dir=DEFAULT_PROCESSED_DIR,
            run_id=job.id,
            chain=get_chain(job.chain),
            progress_callback=on_progress,
        )
    except Exception as exc:  # noqa: BLE001 - Job-Fehler muss sichtbar werden, darf den Thread nicht crashen lassen
        with job.lock:
            job.state = "error"
            job.error = str(exc)
            job.finished_at = datetime.now(timezone.utc)
        _persist(job)
        return

    with job.lock:
        job.csv_path = csv_path
        job.json_path = json_path
        job.transactions = validated
        job.total_transactions = len(validated)
        job.unclassified_count = sum(1 for tx in validated if tx.category == TxCategory.UNCLASSIFIED)
        job.state = "done"
        job.stage = None
        job.finished_at = datetime.now(timezone.utc)
    _persist(job)


def _handle_progress_event(job: Job, event: dict[str, Any]) -> None:
    event_type = event.get("event")

    with job.lock:
        if event_type == "stage":
            job.stage = event.get("stage")
            return

        address = event.get("address")
        if address is None or address not in job.address_progress:
            return
        categories = job.address_progress[address].categories

        if event_type == "category_start":
            category = event["category"]
            categories.setdefault(category, CategoryProgress()).status = "in_progress"
        elif event_type == "category_page":
            category = event["category"]
            cat_progress = categories.setdefault(category, CategoryProgress())
            cat_progress.pages_fetched += 1
            cat_progress.records_fetched += event.get("page_count", 0)
        elif event_type == "category_done":
            category = event["category"]
            cat_progress = categories.setdefault(category, CategoryProgress())
            cat_progress.status = "done"
            cat_progress.records_fetched = event.get("count", cat_progress.records_fetched)
        elif event_type == "category_error":
            category = event["category"]
            cat_progress = categories.setdefault(category, CategoryProgress())
            cat_progress.status = "error"
            cat_progress.error = event.get("error")


def filter_and_paginate(
    job: Job,
    category: str | None,
    min_confidence: float | None,
    search: str | None,
    sort: str | None,
    order: str,
    page: int,
    page_size: int,
) -> tuple[list[CanonicalTransaction], int]:
    """Rein serverseitige Filterung/Sortierung/Pagination - bei
    Grosslaeufen (siehe vitalik.eth-Testlauf: 446.829 Zeilen) darf niemals
    der komplette Datensatz auf einmal ans Frontend gehen."""
    with job.lock:
        items = list(job.transactions)

    if category:
        items = [t for t in items if t.category.value == category]
    if min_confidence is not None:
        items = [t for t in items if t.confidence >= min_confidence]
    if search:
        needle = search.lower()
        items = [
            t
            for t in items
            if needle in t.tx_hash.lower()
            or needle in t.from_address.lower()
            or needle in (t.to_address or "").lower()
        ]

    sort_key = SORTABLE_FIELDS.get(sort or DEFAULT_SORT, SORTABLE_FIELDS[DEFAULT_SORT])
    items.sort(key=sort_key, reverse=(order == "desc"))

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


def to_status_response(job: Job) -> dict[str, Any]:
    """Baut das Status-Response-Dict (wird von routers/imports.py in
    JobStatusResponse validiert). Dict statt direktem Pydantic-Objekt hier,
    um jobs.py nicht an api/schemas.py zu koppeln als Rueckgabetyp."""
    with job.lock:
        return {
            "job_id": job.id,
            "chain": job.chain,
            "state": job.state,
            "stage": job.stage,
            "addresses": {
                addr: {
                    "address": addr,
                    "categories": {
                        cat: {
                            "category": cat,
                            "status": cp.status,
                            "pages_fetched": cp.pages_fetched,
                            "records_fetched": cp.records_fetched,
                            "error": cp.error,
                        }
                        for cat, cp in progress.categories.items()
                    },
                }
                for addr, progress in job.address_progress.items()
            },
            "total_transactions": job.total_transactions,
            "unclassified_count": job.unclassified_count,
            "error": job.error,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "csv_available": job.csv_path is not None,
            "json_available": job.json_path is not None,
        }
