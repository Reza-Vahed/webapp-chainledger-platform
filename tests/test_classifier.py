"""Tests für die Klassifikation kanonischer Transaktionen.

Fokus: Konservatives Verhalten bei Mehrdeutigkeit (kein Raten), korrekte
Swap-Erkennung über mehrere Legs im selben tx_hash, Allowlist-basierte
Staking-/Airdrop-Erkennung.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.classifier import KNOWN_STAKING_CONTRACTS, classify_transactions
from src.models import CanonicalTransaction, SourceRecordType, TxCategory

WALLET = "0x1111111111111111111111111111111111111111"
COUNTERPARTY = "0x2222222222222222222222222222222222222222"


def make_tx(**overrides) -> CanonicalTransaction:
    defaults = dict(
        wallet_address=WALLET,
        tx_hash="0xhash",
        record_type=SourceRecordType.NORMAL,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        block_number=1,
        from_address=COUNTERPARTY,
        to_address=WALLET,
        direction="in",
        amount=Decimal("1"),
        token_symbol="ETH",
        input_data="0x",
    )
    defaults.update(overrides)
    return CanonicalTransaction(**defaults)


def test_plain_eth_transfer_in_is_classified_transfer_in():
    [result] = classify_transactions([make_tx()])
    assert result.category == TxCategory.TRANSFER_IN
    assert result.confidence > 0


def test_plain_eth_transfer_out_is_classified_transfer_out():
    tx = make_tx(from_address=WALLET, to_address=COUNTERPARTY, direction="out")
    [result] = classify_transactions([tx])
    assert result.category == TxCategory.TRANSFER_OUT


def test_erc20_out_and_eth_in_same_hash_is_classified_as_swap():
    erc20_out = make_tx(
        tx_hash="0xswap", record_type=SourceRecordType.ERC20, direction="out",
        from_address=WALLET, to_address="0xrouter00000000000000000000000000000000",
        token_symbol="USDC",
    )
    eth_in = make_tx(
        tx_hash="0xswap", record_type=SourceRecordType.INTERNAL, direction="in",
        from_address="0xrouter00000000000000000000000000000000", to_address=WALLET,
        token_symbol="ETH",
    )
    results = classify_transactions([erc20_out, eth_in])
    assert all(r.category == TxCategory.SWAP for r in results)


def test_erc20_in_and_erc20_out_same_hash_is_classified_as_swap():
    token_out = make_tx(
        tx_hash="0xswap2", record_type=SourceRecordType.ERC20, direction="out",
        from_address=WALLET, to_address="0xrouter00000000000000000000000000000000",
        token_symbol="DAI",
    )
    token_in = make_tx(
        tx_hash="0xswap2", record_type=SourceRecordType.ERC20, direction="in",
        from_address="0xrouter00000000000000000000000000000000", to_address=WALLET,
        token_symbol="USDC",
    )
    results = classify_transactions([token_out, token_in])
    assert all(r.category == TxCategory.SWAP for r in results)


def test_erc20_in_from_known_staking_contract_is_staking_reward():
    staking_contract = next(iter(KNOWN_STAKING_CONTRACTS["ethereum"]))
    tx = make_tx(
        record_type=SourceRecordType.ERC20, direction="in",
        from_address=staking_contract, to_address=WALLET, token_symbol="stETH",
    )
    [result] = classify_transactions([tx])
    assert result.category == TxCategory.STAKING_REWARD
    assert result.confidence >= 0.9


def test_erc20_in_from_known_staking_contract_checksum_case_is_still_matched():
    staking_contract_lower = next(iter(KNOWN_STAKING_CONTRACTS["ethereum"]))
    checksum_case_address = "0x" + "".join(
        c.upper() if i % 2 == 0 else c for i, c in enumerate(staking_contract_lower[2:])
    )
    tx = make_tx(
        record_type=SourceRecordType.ERC20, direction="in",
        from_address=checksum_case_address, to_address=WALLET, token_symbol="stETH",
    )
    [result] = classify_transactions([tx])
    assert result.category == TxCategory.STAKING_REWARD


def test_known_ethereum_staking_contract_is_not_matched_on_a_different_chain():
    """Regression: KNOWN_STAKING_CONTRACTS ist chain-geschlüsselt - eine
    Mainnet-Allowlist-Adresse darf auf einer anderen Chain nicht
    faelschlich als derselbe Vertrag gelten (ungeprueft, spekulativ)."""
    mainnet_staking_contract = next(iter(KNOWN_STAKING_CONTRACTS["ethereum"]))
    tx = make_tx(
        record_type=SourceRecordType.ERC20, direction="in",
        from_address=mainnet_staking_contract, to_address=WALLET, token_symbol="stETH",
        chain="arbitrum",
    )
    [result] = classify_transactions([tx])
    assert result.category != TxCategory.STAKING_REWARD


def test_erc20_in_from_unknown_contract_is_not_guessed_as_staking_or_airdrop():
    tx = make_tx(
        record_type=SourceRecordType.ERC20, direction="in",
        from_address="0x9999999999999999999999999999999999999999", token_symbol="XYZ",
    )
    [result] = classify_transactions([tx])
    # Kein Treffer auf Allowlist -> bleibt ein einfacher Transfer-In,
    # wird NICHT als Airdrop oder Staking-Reward geraten.
    assert result.category == TxCategory.TRANSFER_IN


def test_failed_transaction_is_unclassified_with_warning():
    [result] = classify_transactions([make_tx(is_error=True)])
    assert result.category == TxCategory.UNCLASSIFIED
    assert result.confidence == 0.0
    assert any("manual_review_required" in w for w in result.warnings)


def test_contract_call_without_value_is_contract_interaction():
    tx = make_tx(
        amount=Decimal("0"), input_data="0xa9059cbb0000000000000000000000000",
        from_address=WALLET, to_address="0xcontract000000000000000000000000000000",
        direction="out",
    )
    [result] = classify_transactions([tx])
    assert result.category == TxCategory.CONTRACT_INTERACTION


def test_contract_call_with_value_outside_known_pattern_is_unclassified():
    tx = make_tx(
        amount=Decimal("2"), input_data="0xsomefunctioncall00000000000000000",
        from_address=WALLET, to_address="0xcontract000000000000000000000000000000",
        direction="out",
    )
    [result] = classify_transactions([tx])
    assert result.category == TxCategory.UNCLASSIFIED
    assert any("manual_review_required" in w for w in result.warnings)


def test_internal_transfer_is_transfer_but_flagged_for_review():
    tx = make_tx(record_type=SourceRecordType.INTERNAL, direction="in")
    [result] = classify_transactions([tx])
    assert result.category == TxCategory.TRANSFER_IN
    assert any("manual_review_required" in w for w in result.warnings)
