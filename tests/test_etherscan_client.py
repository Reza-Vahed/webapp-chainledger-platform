"""Tests für den Etherscan-API-Client (Abruf, Pagination, Rate-Limits).

Die HTTP-Session wird als Mock injiziert - es finden keine echten
Netzwerkaufrufe statt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api_client.etherscan_client import EtherscanClient
from src.api_client.exceptions import RateLimitExceededError


def make_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def make_client(session: MagicMock, **overrides) -> EtherscanClient:
    params = dict(
        api_key="TEST_KEY",
        page_size=overrides.pop("page_size", 10),
        max_retries=overrides.pop("max_retries", 3),
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        session=session,
    )
    params.update(overrides)
    return EtherscanClient(**params)


def test_fetch_transactions_single_page_no_more_results():
    session = MagicMock()
    tx = {"hash": "0xabc", "blockNumber": "100", "value": "1000000000000000000"}
    session.get.return_value = make_response({"status": "1", "message": "OK", "result": [tx]})

    client = make_client(session)
    sink_calls = []
    results = client.fetch_transactions(
        "0xWallet", "normal", raw_response_sink=lambda *args: sink_calls.append(args)
    )

    assert results == [tx]
    assert session.get.call_count == 1
    assert len(sink_calls) == 1
    assert sink_calls[0][0] == "normal"  # category wurde korrekt durchgereicht


def test_fetch_transactions_pagination_across_two_pages():
    session = MagicMock()
    page1_txs = [{"hash": f"0x{i}", "blockNumber": "100"} for i in range(2)]
    page2_txs = [{"hash": "0xlast", "blockNumber": "101"}]
    session.get.side_effect = [
        make_response({"status": "1", "message": "OK", "result": page1_txs}),
        make_response({"status": "1", "message": "OK", "result": page2_txs}),
    ]

    client = make_client(session, page_size=2)
    results = client.fetch_transactions("0xWallet", "normal")

    assert [tx["hash"] for tx in results] == ["0x0", "0x1", "0xlast"]
    assert session.get.call_count == 2
    second_call_params = session.get.call_args_list[1].kwargs["params"]
    assert second_call_params["page"] == 2


def test_fetch_transactions_pagination_window_shift_on_hard_limit():
    """Bei Erreichen des Etherscan-Pagination-Fensters (page*offset) muss
    das startblock-Fenster verschoben und die Seitenzählung zurückgesetzt
    werden, statt Transaktionen zu verlieren."""
    session = MagicMock()
    session.get.side_effect = [
        make_response({"status": "1", "message": "OK", "result": [{"hash": "0xa", "blockNumber": "100"}]}),
        make_response({"status": "1", "message": "OK", "result": [{"hash": "0xb", "blockNumber": "101"}]}),
        make_response({"status": "0", "message": "No transactions found", "result": []}),
    ]

    client = make_client(session, page_size=1)
    client.HARD_PAGINATION_WINDOW = 2  # künstlich klein für den Test

    results = client.fetch_transactions("0xWallet", "normal")

    assert [tx["hash"] for tx in results] == ["0xa", "0xb"]
    third_call_params = session.get.call_args_list[2].kwargs["params"]
    assert third_call_params["startblock"] == 101
    assert third_call_params["page"] == 1


def test_fetch_transactions_no_results_returns_empty_list():
    session = MagicMock()
    session.get.return_value = make_response(
        {"status": "0", "message": "No transactions found", "result": []}
    )
    client = make_client(session)

    results = client.fetch_transactions("0xWallet", "erc20")

    assert results == []


def test_rate_limit_retry_then_success(monkeypatch):
    monkeypatch.setattr("src.api_client.etherscan_client.time.sleep", lambda _seconds: None)
    session = MagicMock()
    tx = {"hash": "0xabc", "blockNumber": "100"}
    session.get.side_effect = [
        make_response({"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}),
        make_response({"status": "1", "message": "OK", "result": [tx]}),
    ]
    client = make_client(session, max_retries=3)

    results = client.fetch_transactions("0xWallet", "normal")

    assert results == [tx]
    assert session.get.call_count == 2


def test_rate_limit_retry_recognizes_calls_per_sec_variant(monkeypatch):
    """Regression: Etherscan liefert live u. a. 'Max calls per sec rate
    limit reached (3/sec)' statt der urspruenglich angenommenen exakten
    Formulierung 'Max rate limit reached'. Ein zu enger Marker hat das
    live uebersehen und dadurch bereits erfolgreich abgerufene Seiten
    komplett verworfen statt zu retryen (siehe Live-Testlauf)."""
    monkeypatch.setattr("src.api_client.etherscan_client.time.sleep", lambda _seconds: None)
    session = MagicMock()
    tx = {"hash": "0xabc", "blockNumber": "100"}
    session.get.side_effect = [
        make_response({"status": "0", "message": "NOTOK", "result": "Max calls per sec rate limit reached (3/sec)"}),
        make_response({"status": "1", "message": "OK", "result": [tx]}),
    ]
    client = make_client(session, max_retries=3)

    results = client.fetch_transactions("0xWallet", "normal")

    assert results == [tx]
    assert session.get.call_count == 2


def test_rate_limit_exceeded_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr("src.api_client.etherscan_client.time.sleep", lambda _seconds: None)
    session = MagicMock()
    session.get.return_value = make_response(
        {"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
    )
    client = make_client(session, max_retries=2)

    with pytest.raises(RateLimitExceededError):
        client.fetch_transactions("0xWallet", "normal")

    assert session.get.call_count == 2


def test_api_error_raises_etherscan_api_error():
    from src.api_client.exceptions import EtherscanAPIError

    session = MagicMock()
    session.get.return_value = make_response(
        {"status": "0", "message": "NOTOK", "result": "Error! Invalid address format"}
    )
    client = make_client(session)

    with pytest.raises(EtherscanAPIError):
        client.fetch_transactions("not-an-address", "normal")


def test_missing_api_key_raises_value_error():
    with pytest.raises(ValueError):
        EtherscanClient(api_key="")
