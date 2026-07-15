"""Registry der unterstützten EVM-Chains.

Etherscan API V2 (https://api.etherscan.io/v2/api) deckt mehrere
EVM-kompatible Chains über denselben Endpunkt und denselben API-Key ab -
Chains unterscheiden sich für EtherscanClient ausschließlich über den
Parameter "chainid". Es braucht deshalb keine zweite
BlockchainDataSource-Implementierung, nur eine Konfiguration pro Chain.

Live verifiziert (siehe docs/adr/0004-multi-chain-support.md): Das
Rate-Limit gilt pro API-Key über alle Chains hinweg gemeinsam (identische
Meldung "Max calls per sec rate limit reached (3/sec)" wie bei Ethereum
Mainnet) - deshalb kein chain-spezifischer Rate-Limit-Wert hier.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChainConfig:
    """Konfiguration einer über Etherscan V2 abrufbaren EVM-Chain."""

    key: str
    chain_id: int
    display_name: str
    native_symbol: str
    native_decimals: int
    explorer_name: str


ETHEREUM = ChainConfig(
    key="ethereum",
    chain_id=1,
    display_name="Ethereum Mainnet",
    native_symbol="ETH",
    native_decimals=18,
    explorer_name="Etherscan",
)

ARBITRUM = ChainConfig(
    key="arbitrum",
    chain_id=42161,
    display_name="Arbitrum One",
    native_symbol="ETH",
    native_decimals=18,
    explorer_name="Arbiscan",
)

SUPPORTED_CHAINS: dict[str, ChainConfig] = {
    ETHEREUM.key: ETHEREUM,
    ARBITRUM.key: ARBITRUM,
}

DEFAULT_CHAIN_KEY = ETHEREUM.key


def get_chain(key: str) -> ChainConfig:
    try:
        return SUPPORTED_CHAINS[key]
    except KeyError:
        supported = ", ".join(sorted(SUPPORTED_CHAINS))
        raise ValueError(f"Unbekannte Chain {key!r}. Unterstützt: {supported}") from None
