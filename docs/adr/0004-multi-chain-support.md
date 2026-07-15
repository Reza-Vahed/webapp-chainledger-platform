# ADR 0004: Multi-Chain-Support - Arbitrum One über Etherscan V2

**Status:** Akzeptiert
**Datum:** 2026-07-15

## Kontext

Phase 3 verlangt Unterstützung für mindestens eine weitere EVM-kompatible
Chain zusätzlich zu Ethereum Mainnet, ohne die bestehende
`BlockchainDataSource`-Abstraktion (`src/api_client/base.py`) neu zu
bauen, und ohne die chain-übergreifend identische Klassifikationslogik
(`src/classifier.py`) zu verändern. Zwei Kandidaten wurden verglichen:
Polygon PoS (chainid 137) und Arbitrum One (chainid 42161).

Entscheidender Fund vor der Implementierung: `EtherscanClient` nutzt
bereits die **Etherscan API V2** (`https://api.etherscan.io/v2/api`),
die `chainid` als Parameter akzeptiert und 50+ EVM-Chains - darunter
sowohl Polygon als auch Arbitrum - über denselben Endpunkt und denselben
API-Key abdeckt. Es musste also kein zweiter Client gebaut werden,
sondern nur eine Chain-Konfiguration (`src/api_client/chains.py`).

## Entscheidung

**Arbitrum One** (chainid `42161`) wird als zweite unterstützte Chain
implementiert, über dieselbe `EtherscanClient`-Klasse mit einer
`ChainConfig` aus einer neuen Registry (`src/api_client/chains.py`).

## Begründung

- **Natives Gas-Token identisch zu Mainnet (ETH):** Arbitrum One
  verwendet ETH als Gas-Token, nicht ein separates natives Token wie
  Polygons MATIC. Das vermeidet einen konkreten Sonderfall: Polygons
  natives Token wurde 2024 von MATIC auf POL umbenannt (Token-Migration),
  wodurch je nach Zeitraum einer Wallet-Historie beide Symbole in
  Rohdaten auftreten könnten. Diese Mehrdeutigkeit hätte laut
  Aufgabenstellung nicht spekulativ gelöst werden dürfen - Arbitrum
  vermeidet das Problem strukturell, statt es zu lösen.
- **Gleiche Adresse, direkt nachprüfbar:** EOA-Adressen sind
  chain-übergreifend identisch. Die bestehende Akzeptanztest-Adresse
  `vitalik.eth` konnte unverändert für den Arbitrum-Akzeptanztest
  wiederverwendet werden (siehe README) - keine neue Referenzadresse
  nötig, direkte Vergleichbarkeit mit dem Mainnet-Beispiel.
- **Zielgruppenrelevanz:** Arbitrum ist der nach TVL größte
  Ethereum-L2, mit hoher Retail-/DeFi-Nutzung gerade wegen niedriger
  Gebühren - ein realistischer zweiter Steuerfall für
  DACH-Krypto-Mandanten (häufig: ETH/Token zwischen Mainnet und L2
  gebridged).
- **Kein neuer API-Key nötig:** Da Etherscan V2 denselben Key
  chain-übergreifend verwendet, entfällt ein zusätzlicher
  Registrierungs-/Konfigurationsschritt für Nutzer (`.env.example`
  unverändert bzgl. Secrets).

## Live-Verifikation (nicht nur aus der Dokumentation übernommen)

Wie beim ursprünglichen Etherscan-Rate-Limit-Fall (ADR 0002) wurde das
tatsächliche Verhalten gegen die echte API geprüft, nicht nur die
Dokumentation zugrunde gelegt:

- **Aktivität von `vitalik.eth` auf Arbitrum:** vor der Implementierung
  live geprüft (`txlist`/`txlistinternal`/`tokentx`, chainid 42161) -
  bereits die erste Seite war für `normal` und `tokentx` mit 1000
  Einträgen voll, `internal` lieferte 70 Einträge. Ausreichend aktiv für
  denselben "große/aktive Wallet"-Akzeptanztest wie bei Mainnet (siehe
  README für die finalen Zahlen aus dem vollständigen Lauf).
- **Rate-Limit:** 15 echte parallele Requests gegen `chainid=42161`
  ausgelöst - 12 von 15 wurden gedrosselt, mit exakt derselben Meldung
  wie auf Mainnet: `"Max calls per sec rate limit reached (3/sec)"`.
  Das belegt: das Rate-Limit gilt **pro API-Key über alle Chains
  hinweg gemeinsam**, nicht pro Chain. `ChainConfig` enthält deshalb
  bewusst **keinen** chain-spezifischen Rate-Limit-Wert - der
  bestehende globale Default (3 req/s, `ETHERSCAN_RATE_LIMIT_RPS`)
  gilt unverändert für alle Chains.

## Architekturauswirkung

- `src/api_client/chains.py` (neu): reine Konfiguration (`ChainConfig`:
  `chain_id`, natives Symbol/Decimals, Anzeigename), keine neue
  `BlockchainDataSource`-Implementierung.
- `src/normalizer.py`: natives Symbol/Decimals wurden parametrisiert
  (vorher fest auf `"ETH"`/18 verdrahtet) - Default bleibt unverändert,
  rückwärtskompatibel zu bestehenden Aufrufern.
- `src/classifier.py`: `KNOWN_STAKING_CONTRACTS`/`KNOWN_AIRDROP_CONTRACTS`
  wurden chain-geschlüsselt (`dict[chain_key, dict[address, name]]`), da
  Mainnet-Contract-Adressen (z. B. Lido stETH) auf einer anderen Chain
  nicht automatisch denselben Vertrag bedeuten. Für Arbitrum ist die
  Staking-Allowlist bewusst leer (keine recherchierten Adressen) -
  Treffer fallen konsequent auf `Unklassifiziert` zurück statt zu raten,
  konsistent mit dem bereits bestehenden Airdrop-Allowlist-Prinzip.
- Klassifikationslogik selbst (`_classify_single`) wurde nicht verändert
  - bestätigt, dass sie bereits chain-übergreifend identisch war.

## Verworfene Alternativen

- **Polygon PoS (chainid 137):** technisch ebenso einfach über Etherscan
  V2 abrufbar, aber die MATIC→POL-Migration hätte eine zusätzliche,
  zeitabhängige Fallunterscheidung im Normalizer erfordert, die ohne
  verlässliche Recherche zum genauen Umstellungsblock nicht spekulationsfrei
  umsetzbar gewesen wäre. Guter Kandidat für eine spätere Phase, wenn
  diese Recherche nachgeholt wird.
- **Eigener zweiter Client (z. B. Arbiscan-natives REST-API vor der
  Etherscan-V2-Vereinheitlichung):** hätte Pagination-/Rate-Limit-Logik
  dupliziert, die `EtherscanClient` bereits robust abdeckt - klar gegen
  die Vorgabe "bestehende Abstraktion wiederverwenden, nicht neu bauen".
