"""Test für die Rohdaten-Persistenz des CLI-Orchestrators.

Prüft die konkrete Anforderung "API-Rohantworten unverändert unter
data/raw/ speichern" (Auditierbarkeit) - unabhängig vom API-Client selbst.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.cli import make_raw_sink


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
