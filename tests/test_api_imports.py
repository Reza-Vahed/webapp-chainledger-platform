"""Integrationstests für die Web-API (api/).

Nutzt einen Fake-Etherscan-Client (kein echter Netzwerkzugriff, kein
API-Key nötig) via FastAPI dependency_overrides. Der Job läuft in einem
echten Hintergrund-Thread (siehe api/jobs.py) - Tests pollen daher kurz
auf den Abschluss statt synchron zu blockieren.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import jobs
from api.dependencies import get_import_client
from api.main import app

WALLET = "0x1111111111111111111111111111111111111111"
COUNTERPARTY = "0x2222222222222222222222222222222222222222"


class _FakeClient:
    """Liefert genau eine normale ETH-Transaktion, keine internen/ERC20-
    Transfers - reicht, um die komplette Pipeline durchzuspielen."""

    def fetch_transactions(
        self, address: str, category: str, raw_response_sink=None
    ) -> list[dict[str, Any]]:
        if category == "normal":
            result = [
                {
                    "hash": "0xabc",
                    "blockNumber": "18000000",
                    "timeStamp": "1700000000",
                    "from": COUNTERPARTY,
                    "to": address,
                    "value": "1000000000000000000",
                    "gas": "21000",
                    "gasPrice": "20000000000",
                    "gasUsed": "21000",
                    "isError": "0",
                    "input": "0x",
                }
            ]
        else:
            result = []

        data = {"status": "1", "message": "OK", "result": result}
        if raw_response_sink is not None:
            raw_response_sink(category, address, 1, data)
        return result


class _MultiTxFakeClient:
    """Liefert zwei normale Transaktionen mit unterschiedlichem Betrag/
    Zeitstempel - fuer Sortier-Tests."""

    def fetch_transactions(
        self, address: str, category: str, raw_response_sink=None
    ) -> list[dict[str, Any]]:
        if category == "normal":
            result = [
                {
                    "hash": "0xsmall",
                    "blockNumber": "18000000",
                    "timeStamp": "1700000000",
                    "from": COUNTERPARTY,
                    "to": address,
                    "value": "1000000000000000000",  # 1 ETH
                    "gas": "21000",
                    "gasPrice": "20000000000",
                    "gasUsed": "21000",
                    "isError": "0",
                    "input": "0x",
                },
                {
                    "hash": "0xbig",
                    "blockNumber": "18000001",
                    "timeStamp": "1700001000",
                    "from": COUNTERPARTY,
                    "to": address,
                    "value": "5000000000000000000",  # 5 ETH
                    "gas": "21000",
                    "gasPrice": "20000000000",
                    "gasUsed": "21000",
                    "isError": "0",
                    "input": "0x",
                },
            ]
        else:
            result = []

        data = {"status": "1", "message": "OK", "result": result}
        if raw_response_sink is not None:
            raw_response_sink(category, address, 1, data)
        return result


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(jobs, "DEFAULT_RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(jobs, "DEFAULT_PROCESSED_DIR", tmp_path / "processed")
    app.dependency_overrides[get_import_client] = lambda: _FakeClient()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _wait_for_completion(client: TestClient, job_id: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/imports/{job_id}").json()
        if status["state"] in ("done", "error"):
            return status
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} wurde nicht rechtzeitig abgeschlossen")


def test_health_endpoint(client: TestClient):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_import_rejects_empty_address_list(client: TestClient):
    resp = client.post("/api/v1/imports", json={"addresses": []})
    assert resp.status_code == 422


def test_get_unknown_job_returns_404(client: TestClient):
    resp = client.get("/api/v1/imports/does-not-exist")
    assert resp.status_code == 404


def test_full_import_lifecycle(client: TestClient):
    create_resp = client.post("/api/v1/imports", json={"addresses": [WALLET]})
    assert create_resp.status_code == 202
    job_id = create_resp.json()["job_id"]

    status = _wait_for_completion(client, job_id)
    assert status["state"] == "done"
    assert status["total_transactions"] == 1
    assert status["csv_available"] is True
    assert status["json_available"] is True
    assert status["addresses"][WALLET]["categories"]["normal"]["status"] == "done"

    tx_resp = client.get(f"/api/v1/imports/{job_id}/transactions")
    assert tx_resp.status_code == 200
    payload = tx_resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["tx_hash"] == "0xabc"
    assert payload["items"][0]["category"] == "Transfer-In"

    csv_resp = client.get(f"/api/v1/imports/{job_id}/export/csv")
    assert csv_resp.status_code == 200
    assert "0xabc" in csv_resp.text

    json_resp = client.get(f"/api/v1/imports/{job_id}/export/json")
    assert json_resp.status_code == 200
    assert json_resp.json()[0]["tx_hash"] == "0xabc"


def test_transactions_endpoint_before_completion_returns_409(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    # Job manuell im "running"-Zustand registrieren, ohne ihn abzuschliessen.
    job = jobs.Job(id="running-job", addresses=[WALLET], state="running")
    with jobs._jobs_lock:
        jobs._jobs["running-job"] = job

    resp = client.get("/api/v1/imports/running-job/transactions")
    assert resp.status_code == 409


def test_export_unknown_format_returns_400(client: TestClient):
    job = jobs.Job(id="done-job", addresses=[WALLET], state="done")
    with jobs._jobs_lock:
        jobs._jobs["done-job"] = job

    resp = client.get("/api/v1/imports/done-job/export/xml")
    assert resp.status_code == 400


def test_transactions_filtering_by_category(client: TestClient):
    create_resp = client.post("/api/v1/imports", json={"addresses": [WALLET]})
    job_id = create_resp.json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/v1/imports/{job_id}/transactions", params={"category": "Swap"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_transactions_sorting_by_amount(client: TestClient):
    app.dependency_overrides[get_import_client] = lambda: _MultiTxFakeClient()
    create_resp = client.post("/api/v1/imports", json={"addresses": [WALLET]})
    job_id = create_resp.json()["job_id"]
    _wait_for_completion(client, job_id)

    asc = client.get(f"/api/v1/imports/{job_id}/transactions", params={"sort": "amount", "order": "asc"})
    assert [item["tx_hash"] for item in asc.json()["items"]] == ["0xsmall", "0xbig"]

    desc = client.get(f"/api/v1/imports/{job_id}/transactions", params={"sort": "amount", "order": "desc"})
    assert [item["tx_hash"] for item in desc.json()["items"]] == ["0xbig", "0xsmall"]


def test_transactions_default_sort_is_timestamp_desc(client: TestClient):
    app.dependency_overrides[get_import_client] = lambda: _MultiTxFakeClient()
    create_resp = client.post("/api/v1/imports", json={"addresses": [WALLET]})
    job_id = create_resp.json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/v1/imports/{job_id}/transactions")
    assert [item["tx_hash"] for item in resp.json()["items"]] == ["0xbig", "0xsmall"]


def test_create_import_without_chain_field_defaults_to_ethereum(client: TestClient):
    """Rueckwaertskompatibilitaet: bestehende Clients, die kein chain-Feld
    senden, muessen weiterhin funktionieren (Default: ethereum)."""
    create_resp = client.post("/api/v1/imports", json={"addresses": [WALLET]})
    job_id = create_resp.json()["job_id"]

    status = _wait_for_completion(client, job_id)
    assert status["chain"] == "ethereum"

    tx_resp = client.get(f"/api/v1/imports/{job_id}/transactions")
    assert tx_resp.json()["items"][0]["chain"] == "ethereum"


def test_create_import_with_arbitrum_chain_is_tagged_on_transactions(client: TestClient):
    create_resp = client.post("/api/v1/imports", json={"addresses": [WALLET], "chain": "arbitrum"})
    job_id = create_resp.json()["job_id"]

    status = _wait_for_completion(client, job_id)
    assert status["chain"] == "arbitrum"

    tx_resp = client.get(f"/api/v1/imports/{job_id}/transactions")
    assert tx_resp.json()["items"][0]["chain"] == "arbitrum"


def test_create_import_rejects_unknown_chain(client: TestClient):
    resp = client.post("/api/v1/imports", json={"addresses": [WALLET], "chain": "not-a-real-chain"})
    assert resp.status_code == 422
