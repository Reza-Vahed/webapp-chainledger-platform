"""Etherscan-Implementierung der BlockchainDataSource.

Read-only: Es werden ausschließlich öffentliche GET-Endpunkte der
Etherscan-API angesprochen. Es gibt keinerlei Code-Pfad, der Private Keys,
Seed-Phrasen oder Zugangsdaten entgegennimmt, speichert oder Transaktionen
signiert/sendet.

Deckt drei Kategorien ab (MVP-Scope):
- "normal":   account/txlist          (reguläre ETH-Transaktionen)
- "internal": account/txlistinternal  (interne Transfers)
- "erc20":    account/tokentx         (ERC-20 Token-Transfers)

NFT-Transfers (tokennfttx / token1155tx) werden bewusst NICHT abgerufen -
außerhalb des MVP-Scope.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from src.api_client.base import BlockchainDataSource, RawResponseSink, TransactionCategory
from src.api_client.exceptions import EtherscanAPIError, RateLimitExceededError

logger = logging.getLogger(__name__)


class RateLimiter:
    """Einfacher Sleep-basierter Rate-Limiter (nicht thread-safe - für dieses
    sequenzielle CLI-Tool ausreichend)."""

    def __init__(self, requests_per_second: float) -> None:
        self._min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._last_call: float | None = None

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        if self._last_call is not None:
            remaining = self._min_interval - (now - self._last_call)
            if remaining > 0:
                time.sleep(remaining)
        self._last_call = time.monotonic()


class EtherscanClient(BlockchainDataSource):
    """Read-only Etherscan-Client mit Pagination- und Rate-Limit-Handling."""

    DEFAULT_BASE_URL = "https://api.etherscan.io/v2/api"
    DEFAULT_CHAIN_ID = 1  # Ethereum Mainnet
    DEFAULT_PAGE_SIZE = 1000
    # Etherscan erlaubt page * offset nur bis zu diesem Fenster; danach muss
    # das startblock-Fenster verschoben werden, um weitere Treffer zu sehen.
    HARD_PAGINATION_WINDOW = 10_000

    ACTION_BY_CATEGORY: dict[TransactionCategory, str] = {
        "normal": "txlist",
        "internal": "txlistinternal",
        "erc20": "tokentx",
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        chain_id: int = DEFAULT_CHAIN_ID,
        rate_limit_rps: float = 3.0,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_retries: int = 5,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ETHERSCAN_API_KEY fehlt - siehe .env.example")
        self.api_key = api_key
        self.base_url = base_url
        self.chain_id = chain_id
        self.page_size = page_size
        self.max_retries = max_retries
        self.timeout = timeout_seconds
        self._base_backoff = base_backoff_seconds
        self._max_backoff = max_backoff_seconds
        self._rate_limiter = RateLimiter(rate_limit_rps)
        self._session = session or requests.Session()

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "EtherscanClient":
        """Baut einen Client aus Umgebungsvariablen / einer .env-Datei.

        Lädt niemals einen API-Key mit Default - fehlt der Key, wird
        explizit ein Fehler geworfen statt stillschweigend zu raten.
        """
        load_dotenv(dotenv_path=env_file)
        api_key = os.environ.get("ETHERSCAN_API_KEY")
        if not api_key:
            raise ValueError(
                "ETHERSCAN_API_KEY nicht gesetzt. Bitte .env anlegen (siehe .env.example)."
            )
        return cls(
            api_key=api_key,
            base_url=os.environ.get("ETHERSCAN_BASE_URL", cls.DEFAULT_BASE_URL),
            chain_id=int(os.environ.get("ETHERSCAN_CHAIN_ID", cls.DEFAULT_CHAIN_ID)),
            rate_limit_rps=float(os.environ.get("ETHERSCAN_RATE_LIMIT_RPS", 3.0)),
        )

    def fetch_transactions(
        self,
        address: str,
        category: TransactionCategory,
        raw_response_sink: RawResponseSink | None = None,
    ) -> list[dict[str, Any]]:
        action = self.ACTION_BY_CATEGORY[category]
        results: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        startblock = 0
        endblock = 99_999_999
        page = 1

        while True:
            params = {
                "chainid": self.chain_id,
                "module": "account",
                "action": action,
                "address": address,
                "startblock": startblock,
                "endblock": endblock,
                "page": page,
                "offset": self.page_size,
                "sort": "asc",
                "apikey": self.api_key,
            }
            data = self._get(params)

            if raw_response_sink is not None:
                raw_response_sink(category, address, page, data)

            status = data.get("status")
            message = str(data.get("message", ""))
            result = data.get("result")

            if status == "0":
                if message.lower() == "no transactions found":
                    logger.info(
                        "Keine (weiteren) Transaktionen: category=%s address=%s page=%s",
                        category, address, page,
                    )
                    break
                raise EtherscanAPIError(
                    f"Etherscan-Fehler für action={action} page={page}: "
                    f"message={message!r} result={result!r}"
                )

            if not isinstance(result, list):
                raise EtherscanAPIError(
                    f"Unerwartetes Antwortformat für action={action} page={page}: {result!r}"
                )

            new_count = 0
            for tx in result:
                dedupe_key = json.dumps(tx, sort_keys=True)
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                results.append(tx)
                new_count += 1

            logger.info(
                "Seite abgerufen: category=%s address=%s page=%s empfangen=%s neu=%s gesamt=%s",
                category, address, page, len(result), new_count, len(results),
            )

            if len(result) < self.page_size:
                break  # letzte Seite erreicht

            if page * self.page_size >= self.HARD_PAGINATION_WINDOW:
                # Etherscan-Pagination-Fenster ausgeschöpft: Fenster über
                # startblock verschieben und Seitenzählung zurücksetzen.
                # Der letzte Block wird bewusst erneut abgefragt (statt +1),
                # um Transaktionen im selben Block nicht zu verlieren;
                # exakte Duplikate werden über seen_keys herausgefiltert.
                last_block = int(result[-1]["blockNumber"])
                logger.info(
                    "Pagination-Fenster (%s) erreicht, verschiebe startblock auf %s",
                    self.HARD_PAGINATION_WINDOW, last_block,
                )
                startblock = last_block
                page = 1
                continue

            page += 1

        return results

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            self._rate_limiter.wait()
            try:
                logger.debug(
                    "API-Aufruf: action=%s page=%s attempt=%s/%s",
                    params.get("action"), params.get("page"), attempt, self.max_retries,
                )
                response = self._session.get(self.base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                last_exception = exc
                logger.warning(
                    "Netzwerk-/Parsing-Fehler bei Etherscan-Aufruf (Versuch %s/%s): %s",
                    attempt, self.max_retries, exc,
                )
                self._sleep_backoff(attempt)
                continue

            if self._is_rate_limited(data):
                logger.warning(
                    "Etherscan Rate-Limit erreicht (Versuch %s/%s): %s",
                    attempt, self.max_retries, data.get("result"),
                )
                self._sleep_backoff(attempt)
                continue

            return data

        raise RateLimitExceededError(
            f"Etherscan-Aufruf nach {self.max_retries} Versuchen fehlgeschlagen. "
            f"Letzter Fehler: {last_exception}"
        )

    @staticmethod
    def _is_rate_limited(data: dict[str, Any]) -> bool:
        if data.get("status") != "0":
            return False
        # Bewusst auf den gemeinsamen Kern-Teilstring geprueft, nicht auf die
        # exakte Formulierung: Etherscan verwendet je nach Limit-Typ leicht
        # unterschiedliche Meldungen, u. a. "Max rate limit reached" UND
        # "Max calls per sec rate limit reached (3/sec)" (live beobachtet -
        # ein zu enger exakter Marker hat dieses zweite Format uebersehen und
        # dadurch einen erfolgreichen Teil-Abruf faelschlich als harten
        # Fehler behandelt statt zu retryen).
        marker = "rate limit reached"
        message = str(data.get("message", "")).lower()
        result = str(data.get("result", "")).lower()
        return marker in message or marker in result

    def _sleep_backoff(self, attempt: int) -> None:
        delay = min(self._base_backoff * (2 ** (attempt - 1)), self._max_backoff)
        time.sleep(delay)
