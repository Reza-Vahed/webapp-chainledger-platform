"""FastAPI-Dependencies.

Kapselt den Etherscan-Client als Prozess-Singleton, damit der API-Key nur
einmal aus .env gelesen wird und ausschließlich hier (serverseitig)
existiert - das Frontend kennt nie mehr als die eigene Backend-URL.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from src.api_client.etherscan_client import EtherscanClient


@lru_cache(maxsize=1)
def _build_client() -> EtherscanClient:
    return EtherscanClient.from_env()


def get_etherscan_client() -> EtherscanClient:
    try:
        return _build_client()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Server nicht konfiguriert: {exc}") from exc
