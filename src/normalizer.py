"""Normalisiert rohe Etherscan-Antworten (txlist/txlistinternal/tokentx) in
das kanonische CanonicalTransaction-Modell.

Bewusste Trennung von Verantwortlichkeiten: Der Normalizer führt reine
Formatkonvertierung durch (Einheiten, Zeitstempel, Feldnamen) - KEINE
Interpretation der wirtschaftlichen Bedeutung. Das übernimmt classifier.py.

Fehlerhafte/unerwartete Rohdatensätze werden übersprungen und geloggt statt
stillschweigend mit Default-Werten "repariert" zu werden.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from src.models import CanonicalTransaction, SourceRecordType

logger = logging.getLogger(__name__)

ETH_SYMBOL = "ETH"
ETH_DECIMALS = 18
EMPTY_INPUT_VALUES = (None, "", "0x", "0X")


def normalize_transactions(
    raw_txs: Iterable[dict[str, Any]],
    record_type: SourceRecordType,
    wallet_address: str,
    source: str = "etherscan",
    chain: str = "ethereum",
    native_symbol: str = ETH_SYMBOL,
    native_decimals: int = ETH_DECIMALS,
) -> list[CanonicalTransaction]:
    """Normalisiert eine Liste roher API-Datensätze EINER Kategorie für
    EINE Wallet. Reihenfolge der Eingabe bleibt erhalten.

    native_symbol/native_decimals gelten für "normal"/"internal" (das
    native Gas-Token der jeweiligen Chain, siehe src/api_client/chains.py)
    - ERC20-Transfers lesen Symbol/Decimals weiterhin aus den Rohdaten,
    unabhängig von der Chain.
    """
    wallet_lower = wallet_address.lower()
    normalized: list[CanonicalTransaction] = []

    for raw in raw_txs:
        try:
            tx = _normalize_single(
                raw, record_type, wallet_lower, wallet_address, source, chain, native_symbol, native_decimals
            )
        except (KeyError, InvalidOperation, ValueError, TypeError) as exc:
            logger.warning(
                "Überspringe fehlerhaften Rohdatensatz (record_type=%s hash=%s): %s",
                record_type.value, raw.get("hash"), exc,
            )
            continue
        normalized.append(tx)

    return normalized


def _normalize_single(
    raw: dict[str, Any],
    record_type: SourceRecordType,
    wallet_lower: str,
    wallet_address: str,
    source: str,
    chain: str,
    native_symbol: str,
    native_decimals: int,
) -> CanonicalTransaction:
    from_addr = str(raw.get("from", "")).lower()
    to_addr_raw = raw.get("to")
    to_addr = str(to_addr_raw).lower() if to_addr_raw else None

    direction: str = "out" if from_addr == wallet_lower else "in"
    wallet_in_from_or_to = wallet_lower in (from_addr, to_addr or "")

    timestamp = _parse_timestamp(raw["timeStamp"])
    block_number = int(raw["blockNumber"])
    is_error = str(raw.get("isError", "0")) == "1"

    warnings: list[str] = []
    if not wallet_in_from_or_to:
        # Sollte im Normalfall nicht vorkommen (Query war nach Wallet
        # gefiltert) - dennoch explizit markieren statt stillschweigend
        # eine Richtung zu unterstellen.
        warnings.append("manual_review_required: wallet_address weder in from noch to enthalten")
    if is_error:
        warnings.append("manual_review_required: fehlgeschlagene Transaktion (isError=1)")

    gas_fee_eth: Decimal | None = None
    input_data: str | None = None

    if record_type == SourceRecordType.ERC20:
        token_symbol = str(raw.get("tokenSymbol") or "UNKNOWN")
        token_decimals = int(raw.get("tokenDecimal", ETH_DECIMALS))
        amount = _to_decimal(raw.get("value", "0"), token_decimals)
        contract_raw = raw.get("contractAddress")
        token_contract_address = str(contract_raw).lower() if contract_raw else None
    else:
        token_symbol = native_symbol
        token_decimals = native_decimals
        amount = _to_decimal(raw.get("value", "0"), native_decimals)
        token_contract_address = None
        if record_type == SourceRecordType.NORMAL:
            gas_fee_eth = _compute_gas_fee(raw, native_decimals)
            input_data = raw.get("input")

    return CanonicalTransaction(
        wallet_address=wallet_address,
        tx_hash=raw["hash"],
        record_type=record_type,
        source=source,
        chain=chain,
        timestamp=timestamp,
        block_number=block_number,
        from_address=from_addr,
        to_address=to_addr,
        direction=direction,  # type: ignore[arg-type]
        amount=amount,
        token_symbol=token_symbol,
        token_contract_address=token_contract_address,
        token_decimals=token_decimals,
        gas_fee_eth=gas_fee_eth,
        input_data=input_data,
        is_error=is_error,
        warnings=warnings,
    )


def _parse_timestamp(raw_timestamp: str) -> datetime:
    return datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc)


def _to_decimal(raw_value: Any, decimals: int) -> Decimal:
    return Decimal(str(raw_value)) / (Decimal(10) ** decimals)


def _compute_gas_fee(raw: dict[str, Any], native_decimals: int) -> Decimal | None:
    gas_used = raw.get("gasUsed")
    gas_price = raw.get("gasPrice")
    if gas_used is None or gas_price is None:
        return None
    wei_fee = Decimal(str(gas_used)) * Decimal(str(gas_price))
    return wei_fee / (Decimal(10) ** native_decimals)
