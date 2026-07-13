"""Tests für die Normalisierung roher Etherscan-Datensätze in das
kanonische CanonicalTransaction-Modell."""

from __future__ import annotations

from decimal import Decimal

from src.models import SourceRecordType
from src.normalizer import normalize_transactions

WALLET = "0x1111111111111111111111111111111111111111"


def test_normalize_normal_eth_transfer_in():
    raw = {
        "blockNumber": "18000000",
        "timeStamp": "1700000000",
        "hash": "0xabc",
        "from": "0x2222222222222222222222222222222222222222",
        "to": WALLET,
        "value": "1000000000000000000",  # 1 ETH
        "gas": "21000",
        "gasPrice": "20000000000",
        "gasUsed": "21000",
        "isError": "0",
        "input": "0x",
    }

    [tx] = normalize_transactions([raw], SourceRecordType.NORMAL, WALLET)

    assert tx.amount == Decimal("1")
    assert tx.token_symbol == "ETH"
    assert tx.direction == "in"
    assert tx.tx_hash == "0xabc"
    assert tx.warnings == []
    assert tx.gas_fee_eth == Decimal("21000") * Decimal("20000000000") / Decimal(10**18)


def test_normalize_erc20_transfer_out_applies_token_decimals():
    raw = {
        "blockNumber": "18000001",
        "timeStamp": "1700000100",
        "hash": "0xdef",
        "from": WALLET,
        "to": "0x3333333333333333333333333333333333333333",
        "contractAddress": "0x4444444444444444444444444444444444444444",
        "value": "5000000",  # 5 USDC bei 6 Decimals
        "tokenSymbol": "USDC",
        "tokenDecimal": "6",
    }

    [tx] = normalize_transactions([raw], SourceRecordType.ERC20, WALLET)

    assert tx.amount == Decimal("5")
    assert tx.token_symbol == "USDC"
    assert tx.direction == "out"
    assert tx.token_contract_address == "0x4444444444444444444444444444444444444444"
    assert tx.gas_fee_eth is None  # Gas wird nur bei "normal" ausgewiesen


def test_normalize_flags_failed_transaction():
    raw = {
        "blockNumber": "18000002",
        "timeStamp": "1700000200",
        "hash": "0xfail",
        "from": WALLET,
        "to": "0x5555555555555555555555555555555555555555",
        "value": "0",
        "isError": "1",
        "input": "0xabcdef",
        "gas": "21000",
        "gasPrice": "20000000000",
        "gasUsed": "21000",
    }

    [tx] = normalize_transactions([raw], SourceRecordType.NORMAL, WALLET)

    assert tx.is_error is True
    assert any("isError" in w for w in tx.warnings)


def test_normalize_skips_malformed_record_and_logs(caplog):
    raw_valid = {
        "blockNumber": "18000003",
        "timeStamp": "1700000300",
        "hash": "0xgood",
        "from": WALLET,
        "to": "0x6666666666666666666666666666666666666666",
        "value": "1000000000000000000",
        "isError": "0",
        "input": "0x",
        "gas": "21000",
        "gasPrice": "20000000000",
        "gasUsed": "21000",
    }
    raw_broken = {"hash": "0xbroken"}  # fehlende Pflichtfelder (z. B. timeStamp)

    with caplog.at_level("WARNING"):
        results = normalize_transactions([raw_broken, raw_valid], SourceRecordType.NORMAL, WALLET)

    assert len(results) == 1
    assert results[0].tx_hash == "0xgood"
    assert "0xbroken" in caplog.text


def test_normalize_marks_ambiguous_direction_when_wallet_not_in_from_or_to():
    raw = {
        "blockNumber": "18000004",
        "timeStamp": "1700000400",
        "hash": "0xambiguous",
        "from": "0x7777777777777777777777777777777777777777",
        "to": "0x8888888888888888888888888888888888888888",
        "value": "1000000000000000000",
        "isError": "0",
        "input": "0x",
    }

    [tx] = normalize_transactions([raw], SourceRecordType.INTERNAL, WALLET)

    assert any("manual_review_required" in w for w in tx.warnings)
