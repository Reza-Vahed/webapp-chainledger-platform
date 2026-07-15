"""HTTP-Endpunkte für Import-Jobs.

Dünner Wrapper: enthält selbst keine Pipeline-Logik, delegiert an
api/jobs.py (Orchestrierung) bzw. direkt an src/ (Serialisierung via
transaction_to_dict).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from api import jobs
from api.dependencies import get_import_client
from api.schemas import (
    ImportCreatedResponse,
    ImportListResponse,
    ImportRequest,
    ImportSummary,
    JobStatusResponse,
    TransactionOut,
    TransactionsPage,
)
from src.api_client.etherscan_client import EtherscanClient
from src.exporter import transaction_to_dict

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])


@router.post("", response_model=ImportCreatedResponse, status_code=202)
def create_import(
    payload: ImportRequest,
    client: EtherscanClient = Depends(get_import_client),
) -> ImportCreatedResponse:
    job_id = jobs.create_job(payload.addresses, client, payload.chain)
    return ImportCreatedResponse(job_id=job_id)


@router.get("", response_model=ImportListResponse)
def list_imports() -> ImportListResponse:
    """Import-Historie (alle Chains, alle Status), neueste zuerst - für
    die Wiedereröffnen-Ansicht im Frontend."""
    return ImportListResponse(items=[ImportSummary(**item) for item in jobs.list_job_summaries()])


@router.delete("/{job_id}", status_code=204)
def delete_import(job_id: str) -> None:
    job = jobs.get_job(job_id)
    if job is not None and job.state in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"Laufender Job kann nicht gelöscht werden (state={job.state})")
    if not jobs.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job nicht gefunden")


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_import_status(job_id: str) -> JobStatusResponse:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    return JobStatusResponse(**jobs.to_status_response(job))


@router.get("/{job_id}/transactions", response_model=TransactionsPage)
def get_import_transactions(
    job_id: str,
    category: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    search: str | None = None,
    sort: str | None = Query(default=None, pattern="^(timestamp|amount|confidence|category|block_number)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> TransactionsPage:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    if job.state != "done":
        raise HTTPException(status_code=409, detail=f"Job noch nicht abgeschlossen (state={job.state})")

    items, total = jobs.filter_and_paginate(job, category, min_confidence, search, sort, order, page, page_size)
    return TransactionsPage(
        items=[TransactionOut(**transaction_to_dict(tx)) for tx in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}/export/{fmt}")
def download_export(job_id: str, fmt: str) -> FileResponse:
    if fmt not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="fmt muss 'csv' oder 'json' sein")

    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    if job.state != "done":
        raise HTTPException(status_code=409, detail=f"Job noch nicht abgeschlossen (state={job.state})")

    path = job.csv_path if fmt == "csv" else job.json_path
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Export-Datei nicht gefunden")

    media_type = "text/csv" if fmt == "csv" else "application/json"
    return FileResponse(path, media_type=media_type, filename=path.name)
