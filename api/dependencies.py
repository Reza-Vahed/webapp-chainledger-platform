"""FastAPI-Dependencies.

Kapselt den Etherscan-Client als Prozess-Singleton pro Chain, damit der
API-Key nur einmal pro Chain aus .env gelesen wird und ausschließlich
hier (serverseitig) existiert - das Frontend kennt nie mehr als die
eigene Backend-URL. Ein Singleton pro Chain (statt global) genügt, da
Etherscan V2 denselben API-Key für alle Chains verwendet (siehe
src/api_client/chains.py) - trotzdem braucht jede Chain ihre eigene
EtherscanClient-Instanz wegen unterschiedlicher chain_id.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from api.schemas import ImportRequest
from src.api_client.chains import DEFAULT_CHAIN_KEY, get_chain
from src.api_client.etherscan_client import EtherscanClient


@lru_cache(maxsize=None)
def _build_client(chain_key: str) -> EtherscanClient:
    return EtherscanClient.from_env(chain=get_chain(chain_key))


def get_etherscan_client(chain: str = DEFAULT_CHAIN_KEY) -> EtherscanClient:
    try:
        return _build_client(chain)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Server nicht konfiguriert: {exc}") from exc


def get_import_client(payload: ImportRequest) -> EtherscanClient:
    """Wie get_etherscan_client(), aber chain kommt aus dem Request-Body
    (payload.chain) statt aus einem Query-Param/Default - als eigene
    Dependency, damit FastAPI den Body korrekt einmalig auflöst und Tests
    weiterhin per dependency_overrides einen Fake-Client injizieren können."""
    return get_etherscan_client(payload.chain)
