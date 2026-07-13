# ADR 0002: Datenquelle - Etherscan API (V2, Chain ID 1)

**Status:** Akzeptiert
**Datum:** 2026-07-13

## Kontext

Der Agent muss On-Chain-Daten strikt read-only, ohne eigenen Node und ohne
Zugangsdaten/private Keys beziehen. Benötigt werden normale ETH-Transaktionen,
interne Transfers und ERC-20-Transfers für beliebige öffentliche Adressen -
inklusive Pagination und Rate-Limit-Handling.

## Entscheidung

Etherscan API V2 (`https://api.etherscan.io/v2/api`, `chainid=1` für Ethereum
Mainnet), drei Endpunkte:

- `account/txlist` - normale Transaktionen
- `account/txlistinternal` - interne Transfers
- `account/tokentx` - ERC-20 Transfers

Der Zugriff ist in `src/api_client/` hinter dem Interface `BlockchainDataSource`
gekapselt; `EtherscanClient` ist eine austauschbare Implementierung.

## Begründung

- Kostenloser Tier ausreichend (100.000 Requests/Tag) für ein
  Einzel-Wallet-CLI-Tool. Das tatsächliche Sekunden-Limit wich im Live-Test
  von der ursprünglich angenommenen Dokumentation ab (beobachtet:
  `"Max calls per sec rate limit reached (3/sec)"` statt der angenommenen
  5/s) - der Client-Default wurde daraufhin auf 3 req/s gesenkt und das
  Retry-Handling korrigiert (siehe `src/api_client/etherscan_client.py`,
  `_is_rate_limited`), da der ursprüngliche Marker-String diese konkrete
  Fehlermeldungsvariante nicht erkannt hatte.
- Gut dokumentiert, De-facto-Standard für Ethereum-Block-Explorer-Daten;
  auch von etablierten Steuer-Tools (Blockpit, CoinTracking) selbst genutzt -
  erleichtert den späteren manuellen Abgleich.
- Deckt alle drei benötigten MVP-Kategorien über einheitliche, gut
  dokumentierte REST-Endpunkte ab; NFT-Endpunkte (`tokennfttx`,
  `token1155tx`) werden bewusst nicht angesprochen (außerhalb MVP-Scope).
- Durch das Interface `BlockchainDataSource` bleibt die Datenquelle
  austauschbar (z. B. gegen Alchemy/Infura oder einen eigenen Node), ohne
  Normalizer, Classifier, Validator oder CLI anzupassen.

## Verworfene Alternativen

- **Eigener Ethereum-Node (Infura/Alchemy JSON-RPC + manuelles Log-Parsing):**
  deutlich höherer Implementierungsaufwand (Blockweise Iteration, ABI-Decoding
  für ERC-20-Events) für den MVP nicht gerechtfertigt; Etherscan liefert diese
  Aggregation bereits fertig.
- **The Graph / Subgraphs:** mächtig für komplexe Abfragen, aber zusätzliche
  Infrastruktur-/Lernkurve, die für drei einfache Account-Abfragen im MVP
  nicht nötig ist.
- **Mehrere Provider parallel (Fallback-Strategie):** zu diesem Zeitpunkt
  Over-Engineering; das Interface erlaubt einen späteren Wechsel bei Bedarf,
  ohne ihn im MVP vorwegzunehmen.
