"""Tests für den CSV-/JSON-Export der kanonischen Transaktionen."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.exporter import export_transactions
from src.models import CanonicalTransaction, SourceRecordType, TxCategory

WALLET = "0x1111111111111111111111111111111111111111"
COUNTERPARTY = "0x2222222222222222222222222222222222222222"


def make_tx(**overrides) -> CanonicalTransaction:
    defaults = dict(
        wallet_address=WALLET,
        tx_hash="0xhash",
        record_type=SourceRecordType.NORMAL,
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        block_number=100,
        from_address=COUNTERPARTY,
        to_address=WALLET,
        direction="in",
        amount=Decimal("0.000000000000000001"),  # 1 Wei - Praezisionstest
        token_symbol="ETH",
        gas_fee_eth=Decimal("0.00042"),
        category=TxCategory.TRANSFER_IN,
        confidence=0.9,
        warnings=["manual_review_required: Beispiel"],
    )
    defaults.update(overrides)
    return CanonicalTransaction(**defaults)


def test_export_creates_csv_and_json_with_matching_row_count(tmp_path: Path):
    txs = [make_tx(tx_hash="0xa"), make_tx(tx_hash="0xb", direction="out", from_address=WALLET, to_address=COUNTERPARTY)]

    csv_path, json_path = export_transactions(txs, tmp_path, run_id="20240101T000000Z")

    assert csv_path.exists()
    assert json_path.exists()

    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with json_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    assert len(rows) == 2
    assert len(payload) == 2


def test_export_preserves_decimal_precision_as_string(tmp_path: Path):
    tx = make_tx(amount=Decimal("0.000000000000000001"))  # 1 Wei

    csv_path, json_path = export_transactions([tx], tmp_path, run_id="run1")

    with csv_path.open(encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    with json_path.open(encoding="utf-8") as f:
        [entry] = json.load(f)

    assert row["amount"] == "0.000000000000000001"
    assert entry["amount"] == "0.000000000000000001"


def test_export_json_keeps_warnings_as_native_list_and_csv_joins_them(tmp_path: Path):
    tx = make_tx(warnings=["manual_review_required: a", "data_gap_or_error: b"])

    csv_path, json_path = export_transactions([tx], tmp_path, run_id="run2")

    with csv_path.open(encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    with json_path.open(encoding="utf-8") as f:
        [entry] = json.load(f)

    assert entry["warnings"] == ["manual_review_required: a", "data_gap_or_error: b"]
    assert row["warnings"] == "manual_review_required: a; data_gap_or_error: b"


def test_export_includes_required_audit_fields(tmp_path: Path):
    tx = make_tx()
    _, json_path = export_transactions([tx], tmp_path, run_id="run3")

    with json_path.open(encoding="utf-8") as f:
        [entry] = json.load(f)

    for field in ("tx_hash", "confidence", "warnings", "source", "category"):
        assert field in entry


def test_export_sorts_by_wallet_and_timestamp(tmp_path: Path):
    early = make_tx(tx_hash="0xearly", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
    late = make_tx(tx_hash="0xlate", timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc))

    _, json_path = export_transactions([late, early], tmp_path, run_id="run4")

    with json_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    assert [entry["tx_hash"] for entry in payload] == ["0xearly", "0xlate"]
