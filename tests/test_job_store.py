"""Tests für die SQLite-basierte Job-Metadaten-Persistenz (api/db.py).

Jeder Test nutzt eine eigene tmp_path-DB-Datei - keine geteilte
Prozess-DB, keine Netzwerkaufrufe.
"""

from __future__ import annotations

from pathlib import Path

from api import db


def make_meta(**overrides) -> dict:
    defaults = dict(
        id="job-1",
        chain="ethereum",
        addresses=["0x1111111111111111111111111111111111111111"],
        state="done",
        error=None,
        started_at="2026-07-15T10:00:00+00:00",
        finished_at="2026-07-15T10:05:00+00:00",
        total_transactions=42,
        unclassified_count=1,
        csv_path="/data/processed/transactions_job-1.csv",
        json_path="/data/processed/transactions_job-1.json",
    )
    defaults.update(overrides)
    return defaults


def test_upsert_and_get_job_roundtrip(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.upsert_job(make_meta(), db_path=db_path)

    result = db.get_job("job-1", db_path=db_path)

    assert result is not None
    assert result["chain"] == "ethereum"
    assert result["addresses"] == ["0x1111111111111111111111111111111111111111"]
    assert result["total_transactions"] == 42


def test_get_unknown_job_returns_none(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.upsert_job(make_meta(), db_path=db_path)

    assert db.get_job("does-not-exist", db_path=db_path) is None


def test_upsert_is_idempotent_and_updates_existing_row(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.upsert_job(make_meta(state="queued", total_transactions=None), db_path=db_path)
    db.upsert_job(make_meta(state="done", total_transactions=42), db_path=db_path)

    rows = db.list_jobs(db_path=db_path)

    assert len(rows) == 1
    assert rows[0]["state"] == "done"
    assert rows[0]["total_transactions"] == 42


def test_list_jobs_orders_newest_first(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.upsert_job(make_meta(id="early", started_at="2026-07-15T09:00:00+00:00"), db_path=db_path)
    db.upsert_job(make_meta(id="late", started_at="2026-07-15T11:00:00+00:00"), db_path=db_path)

    rows = db.list_jobs(db_path=db_path)

    assert [row["id"] for row in rows] == ["late", "early"]


def test_delete_job_removes_row_and_reports_existence(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.upsert_job(make_meta(), db_path=db_path)

    assert db.delete_job("job-1", db_path=db_path) is True
    assert db.get_job("job-1", db_path=db_path) is None
    assert db.delete_job("job-1", db_path=db_path) is False


def test_persistence_survives_fresh_connection(tmp_path: Path):
    """Simuliert einen Neustart: eine neue, unabhängige Verbindung zur
    selben Datei muss die zuvor geschriebenen Daten sehen."""
    db_path = tmp_path / "test.db"
    db.upsert_job(make_meta(), db_path=db_path)

    reloaded = db.get_job("job-1", db_path=db_path)

    assert reloaded is not None
    assert reloaded["state"] == "done"
