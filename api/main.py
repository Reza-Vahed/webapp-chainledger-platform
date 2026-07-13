"""FastAPI-Einstiegspunkt: schlanker HTTP-Wrapper um die bestehende
Python-Pipeline (src/). Enthält selbst keine Pipeline-Logik.

Sicherheit: Der Etherscan-API-Key wird ausschließlich hier (serverseitig,
via .env) geladen - siehe api/dependencies.py. Das Frontend kennt nur
diese API, niemals Etherscan direkt.

Lokal starten: uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.imports import router as imports_router

app = FastAPI(title="ChainLedger Platform API", version="1.0.0")

# Nur für lokale Entwicklung (Vite-Dev-Server läuft auf anderem Port als
# FastAPI). Produktions-Konfiguration ist nicht Teil dieser Phase.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
