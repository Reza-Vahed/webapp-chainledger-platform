"""SQLite-basierte Persistenz für Job-Metadaten (siehe api/jobs.py).

Bewusst NUR Metadaten (Adressen, Chain, Status, Zähler, Pfade) - die
validierten Transaktionen selbst liegen bereits vollständig und
unverändert in data/processed/transactions_<job_id>.json (Auditierbarkeits-
Anforderung, siehe src/exporter.py). Das vermeidet Datenduplizierung; beim
Reopen eines abgeschlossenen Jobs nach einem Neustart wird diese Datei
zurückgelesen (siehe api/jobs.py::_load_job_from_store).

Kurzlebige Connections pro Operation (sqlite3-Connections sind nicht
thread-übergreifend teilbar, Jobs laufen in eigenen Threads) - für dieses
Nutzungsvolumen (Einzel-Nutzer-Demo-Tool) ausreichend. WAL-Modus, damit
Status-Polling (häufige Reads) nicht durch gleichzeitige Schreibzugriffe
laufender Jobs blockiert wird.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "chainledger.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    chain TEXT NOT NULL,
    addresses TEXT NOT NULL,
    state TEXT NOT NULL,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    total_transactions INTEGER,
    unclassified_count INTEGER,
    csv_path TEXT,
    json_path TEXT
);
"""

_COLUMNS = (
    "id", "chain", "addresses", "state", "error", "started_at", "finished_at",
    "total_transactions", "unclassified_count", "csv_path", "json_path",
)


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_job(job_meta: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> None:
    """Legt einen Job an oder aktualisiert ihn (Write-Through bei jedem
    Statusübergang, siehe api/jobs.py). job_meta muss alle _COLUMNS-Keys
    enthalten, "addresses" als Liste (wird hier JSON-serialisiert)."""
    params = {**job_meta, "addresses": json.dumps(job_meta["addresses"])}
    placeholders = ", ".join(f":{col}" for col in _COLUMNS)
    updates = ", ".join(f"{col}=excluded.{col}" for col in _COLUMNS if col != "id")
    with _connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO jobs ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            params,
        )


def list_jobs(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY started_at DESC").fetchall()
    return [_row_to_dict(row) for row in rows]


def get_job(job_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def delete_job(job_id: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Löscht die Metadaten-Zeile. Gibt True zurück, wenn ein Job mit
    dieser ID existierte. Löscht KEINE Dateien (siehe api/jobs.py, das
    zusätzlich die zugehörigen Raw-/Export-Dateien entfernt)."""
    with _connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return cursor.rowcount > 0


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["addresses"] = json.loads(data["addresses"])
    return data
