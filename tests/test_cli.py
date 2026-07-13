"""Test für die Rohdaten-Persistenz des CLI-Orchestrators.

Prüft die konkrete Anforderung "API-Rohantworten unverändert unter
data/raw/ speichern" (Auditierbarkeit) - unabhängig vom API-Client selbst.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.cli import make_raw_sink, run_import


def test_raw_sink_persists_response_unmodified(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    sink = make_raw_sink(raw_dir, run_id="20240101T000000Z")

    original_payload = {"status": "1", "message": "OK", "result": [{"hash": "0xabc", "value": "123"}]}
    sink("normal", "0xWALLET0000000000000000000000000000000000", 1, original_payload)

    files = list(raw_dir.glob("*.json"))
    assert len(files) == 1

    with files[0].open(encoding="utf-8") as f:
        persisted = json.load(f)

    assert persisted == original_payload  # unveraendert
    assert "20240101T000000Z" in files[0].name
    assert "normal" in files[0].name


def test_raw_sink_writes_separate_files_per_page(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    sink = make_raw_sink(raw_dir, run_id="run1")

    sink("erc20", "0xWALLET0000000000000000000000000000000000", 1, {"result": []})
    sink("erc20", "0xWALLET0000000000000000000000000000000000", 2, {"result": []})

    files = sorted(raw_dir.glob("*.json"))
    assert len(files) == 2
    assert files[0].name != files[1].name


class _FakeClient:
    """Minimaler Fake, der nur das von run_import benoetigte Interface
    (fetch_transactions) implementiert - kein echter Netzwerkzugriff."""

    def fetch_transactions(
        self, address: str, category: str, raw_response_sink=None
    ) -> list[dict[str, Any]]:
        data = {"status": "1", "message": "OK", "result": []}
        if raw_response_sink is not None:
            raw_response_sink(category, address, 1, data)
        return []


def test_run_import_reports_progress_events_without_breaking_default_behavior(tmp_path: Path):
    """progress_callback ist additiv: run_import muss ohne Callback
    weiterhin normal funktionieren (CLI-Kompatibilitaet), UND bei
    gesetztem Callback die erwarteten Lifecycle-Events liefern (fuer das
    Web-Backend, siehe api/jobs.py)."""
    events: list[dict[str, Any]] = []

    csv_path, json_path, validated = run_import(
        addresses=["0x1111111111111111111111111111111111111111"],
        client=_FakeClient(),
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        run_id="test-run",
        progress_callback=events.append,
    )

    assert validated == []
    assert csv_path.exists()
    assert json_path.exists()

    event_types = [e["event"] for e in events]
    assert "address_start" in event_types
    assert "category_start" in event_types
    assert "category_done" in event_types
    stages = [e["stage"] for e in events if e["event"] == "stage"]
    assert stages == ["classifying", "validating", "exporting"]
    assert event_types[-1] == "done"


def test_run_import_works_without_progress_callback(tmp_path: Path):
    """Ruft run_import wie die bestehende CLI auf (kein Callback) - muss
    unveraendert funktionieren."""
    csv_path, json_path, validated = run_import(
        addresses=["0x1111111111111111111111111111111111111111"],
        client=_FakeClient(),
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        run_id="test-run-2",
    )

    assert validated == []
    assert csv_path.exists()
    assert json_path.exists()
