"""Tests für die Chain-Registry (src/api_client/chains.py).

Fokus: Konsistenz der Registry selbst (eindeutige chain_ids, gültige
Defaults) - Live-Verhalten der Chains wird in etherscan_client-Tests bzw.
manuell gegen die echte API geprüft (siehe docs/adr/0004).
"""

from __future__ import annotations

import pytest

from src.api_client.chains import DEFAULT_CHAIN_KEY, SUPPORTED_CHAINS, get_chain


def test_default_chain_is_ethereum():
    assert DEFAULT_CHAIN_KEY == "ethereum"
    assert DEFAULT_CHAIN_KEY in SUPPORTED_CHAINS


def test_chain_ids_are_unique():
    chain_ids = [c.chain_id for c in SUPPORTED_CHAINS.values()]
    assert len(chain_ids) == len(set(chain_ids))


def test_get_chain_returns_matching_config():
    chain = get_chain("arbitrum")
    assert chain.key == "arbitrum"
    assert chain.chain_id == 42161


def test_get_chain_raises_for_unknown_key():
    with pytest.raises(ValueError):
        get_chain("not-a-real-chain")


def test_all_chains_have_required_fields():
    for key, chain in SUPPORTED_CHAINS.items():
        assert chain.key == key
        assert chain.chain_id > 0
        assert chain.display_name
        assert chain.native_symbol
        assert chain.native_decimals > 0
        assert chain.explorer_name
