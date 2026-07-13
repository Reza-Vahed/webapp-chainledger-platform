"""Tests für die Fehler-/Lücken-Validierung kanonischer Transaktionen.

Prinzip: Der Validator markiert nur (fügt Warnhinweise hinzu), verändert
niemals Beträge/Kategorien - das wird hier explizit mitgeprüft.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.models import CanonicalTransaction, SourceRecordType, TxCategory
from src.validator import ETHEREUM_GENESIS, validate_transactions

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
        gas_fee_eth=Decimal("0.001"),
        category=TxCategory.TRANSFER_IN,
        confidence=0.9,
    )
    defaults.update(overrides)
    return CanonicalTransaction(**defaults)


def test_healthy_transaction_gets_no_extra_warnings():
    tx = make_tx()
    [result] = validate_transactions([tx])
    assert result.warnings == []
    assert result.amount == tx.amount  # unveraendert


def test_duplicate_transactions_are_flagged_but_not_dropped():
    tx1 = make_tx()
    tx2 = make_tx()  # identischer Fingerprint

    results = validate_transactions([tx1, tx2])

    assert len(results) == 2  # kein automatisches Deduplizieren/Loeschen
    assert all(any(w.startswith("data_gap_or_error") for w in r.warnings) for r in results)


def test_failed_transaction_with_positive_amount_is_flagged():
    tx = make_tx(is_error=True, amount=Decimal("1"))
    [result] = validate_transactions([tx])
    assert any("Wertangabe" in w or "Betrag" in w for w in result.warnings)


def test_implausible_timestamp_before_genesis_is_flagged():
    tx = make_tx(timestamp=ETHEREUM_GENESIS - timedelta(days=1))
    [result] = validate_transactions([tx])
    assert any("unplausibler Zeitstempel" in w for w in result.warnings)


def test_future_timestamp_is_flagged():
    tx = make_tx(timestamp=datetime.now(timezone.utc) + timedelta(days=1))
    [result] = validate_transactions([tx])
    assert any("unplausibler Zeitstempel" in w for w in result.warnings)


def test_missing_gas_fee_for_normal_transaction_is_flagged():
    tx = make_tx(record_type=SourceRecordType.NORMAL, gas_fee_eth=None, is_error=False)
    [result] = validate_transactions([tx])
    assert any("Gas-Fee" in w for w in result.warnings)


def test_missing_gas_fee_not_flagged_for_erc20_record():
    tx = make_tx(record_type=SourceRecordType.ERC20, gas_fee_eth=None, token_symbol="USDC")
    [result] = validate_transactions([tx])
    assert not any("Gas-Fee" in w for w in result.warnings)


def test_low_confidence_gets_manual_review_warning():
    tx = make_tx(confidence=0.2, category=TxCategory.UNCLASSIFIED)
    [result] = validate_transactions([tx])
    assert any(w.startswith("manual_review_required") for w in result.warnings)


def test_low_confidence_does_not_duplicate_existing_manual_review_warning():
    tx = make_tx(confidence=0.2, warnings=["manual_review_required: bereits vom Classifier gesetzt"])
    [result] = validate_transactions([tx])
    manual_review_warnings = [w for w in result.warnings if w.startswith("manual_review_required")]
    assert len(manual_review_warnings) == 1
