"""Request-/Response-Modelle der Web-API. Getrennt von src/models.py
(kanonisches Pipeline-Modell), da die API-Sicht (z. B. paginierte Listen,
Job-Status) eine andere Form hat als die interne Datenstruktur.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.api_client.chains import DEFAULT_CHAIN_KEY, SUPPORTED_CHAINS

ChainKey = Literal["ethereum", "arbitrum"]
# Fail fast bei Drift zwischen der Chain-Registry (Quelle der Wahrheit,
# src/api_client/chains.py) und diesem Literal-Type (fuer OpenAPI-Schema
# und Pydantic-Validierung noetig, da Literal keine dynamische Liste erlaubt).
assert set(ChainKey.__args__) == set(SUPPORTED_CHAINS), "ChainKey weicht von SUPPORTED_CHAINS ab"


class ImportRequest(BaseModel):
    addresses: list[str] = Field(..., min_length=1)
    # Default haelt bestehende Clients (ohne chain-Feld) unveraendert
    # lauffaehig - siehe src/api_client/chains.py fuer die Chain-Liste.
    chain: ChainKey = DEFAULT_CHAIN_KEY  # type: ignore[assignment]


class ImportCreatedResponse(BaseModel):
    job_id: str


CategoryStatus = Literal["pending", "in_progress", "done", "error"]
JobState = Literal["queued", "running", "done", "error"]


class CategoryProgressOut(BaseModel):
    category: str
    status: CategoryStatus = "pending"
    pages_fetched: int = 0
    records_fetched: int = 0
    error: str | None = None


class AddressProgressOut(BaseModel):
    address: str
    categories: dict[str, CategoryProgressOut] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    job_id: str
    chain: str
    state: JobState
    stage: str | None = None
    addresses: dict[str, AddressProgressOut] = Field(default_factory=dict)
    total_transactions: int | None = None
    unclassified_count: int | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    csv_available: bool = False
    json_available: bool = False


class TransactionOut(BaseModel):
    wallet_address: str
    chain: str
    tx_hash: str
    timestamp: datetime
    category: str
    direction: str
    amount: str
    token_symbol: str
    token_contract_address: str | None = None
    from_address: str
    to_address: str | None = None
    gas_fee_eth: str | None = None
    confidence: float
    warnings: list[str]
    source: str
    record_type: str
    block_number: int
    is_error: bool


class TransactionsPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class ImportSummary(BaseModel):
    """Eintrag der Import-Historie (GET /api/v1/imports) - Metadaten aus
    der SQLite-Persistenz (api/db.py), unabhängig davon, ob der Job noch
    im Prozess-Speicher liegt."""

    job_id: str
    chain: str
    addresses: list[str]
    state: JobState
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    total_transactions: int | None = None
    unclassified_count: int | None = None
    csv_available: bool = False
    json_available: bool = False


class ImportListResponse(BaseModel):
    items: list[ImportSummary]
