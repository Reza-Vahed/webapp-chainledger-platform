# ChainLedger Platform - On-Chain-Datenimport-Agent (MVP)

🇬🇧 [English version](README.md)

Ein strikt read-only CLI-Tool, das On-Chain-Transaktionsdaten direkt von
öffentlichen Ethereum-Wallet-Adressen abruft, in ein kanonisches Modell
normalisiert, nach einer festen steuerlich relevanten Kategorienliste
klassifiziert, offensichtliche Datenprobleme markiert und als CSV + JSON
für den manuellen Abgleich mit Krypto-Steuer-Tools (z. B. Blockpit,
CoinTracking) exportiert.

Dies ist ein Portfolio-/technisches Validierungsprojekt, **keine**
Steuersoftware.

## Was dieses Tool NICHT tut

- Keine UI, keine Datenbank, keine Multi-Chain-Unterstützung, keine
  KI-Komponenten (MVP-Scope)
- Keine Steuerberechnung, keine FIFO-/Anschaffungskosten-Logik - es
  bereitet Daten nur auf
- Keine NFT-Transfers (ERC-721/1155) - außerhalb des MVP-Scope
- Signiert oder sendet niemals Transaktionen; verarbeitet niemals private
  Keys, Seed-Phrasen oder Exchange-Zugangsdaten - strikt read-only, nur
  öffentliche Daten
- Rät niemals: Mehrdeutige Fälle (z. B. Kauf-/Verkauf-Richtung bei einem
  DEX-Swap) werden immer als `Swap` oder `Unklassifiziert` eingestuft,
  niemals stillschweigend angenommen

## Architektur

```
EtherscanClient (src/api_client/)  ->  rohes JSON (data/raw/, unveraendert)
        |
        v
normalize_transactions (src/normalizer.py)  ->  CanonicalTransaction (pydantic)
        |
        v
classify_transactions (src/classifier.py)   ->  feste Kategorie + Konfidenz
        |
        v
validate_transactions (src/validator.py)    ->  markiert offensichtliche Fehler/Luecken
        |
        v
export_transactions (src/exporter.py)       ->  data/processed/*.csv + *.json
```

Orchestriert durch `src/cli.py`. Die Datenquelle ist hinter
`BlockchainDataSource` (`src/api_client/base.py`) gekapselt, sodass
Etherscan später gegen einen anderen Anbieter ausgetauscht werden kann,
ohne den Rest der Pipeline anzufassen. Die Begründung dieser Entscheidungen
steht in `docs/adr/`.

## Klassifikations-Kategorien

Feste, abschließende Liste (siehe `src/models.py::TxCategory`):
`Transfer-In`, `Transfer-Out`, `Swap`, `Staking-Reward`, `Airdrop`,
`Contract-Interaktion`, `Unklassifiziert`.

- **Swap-Erkennung** gruppiert alle Records mit demselben `tx_hash` und
  sucht nach Mehr-Leg-Mustern (z. B. ERC-20-Out + ETH-In). Die
  Kauf-/Verkauf-Richtung wird nie unterstellt.
- **Staking-Reward / Airdrop** werden nur bei Treffer auf eine kleine,
  explizite Allowlist bekannter Contracts vergeben (`src/classifier.py`).
  Alles andere bleibt `Transfer-In`/`Unklassifiziert` statt geraten zu
  werden. Bekannte Einschränkung: Rebase-Liquid-Staking-Token (z. B.
  stETH) erzeugen nicht immer klassische Transfer-Events, wodurch Rewards
  daraus über die Account-API u. U. nicht vollständig erfasst werden -
  zur manuellen Prüfung markiert.
- Jede Zeile trägt `confidence` (0.0-1.0) und eine `warnings`-Liste (z. B.
  `manual_review_required`, `data_gap_or_error`) - nie stillschweigend
  verworfen.

## Voraussetzungen

- Python 3.11+
- Kostenloser Etherscan-API-Key: https://etherscan.io/apis

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env
# dann .env öffnen und ETHERSCAN_API_KEY=<dein Key> eintragen
```

## Tests ausführen

```bash
pytest tests/ -v
```

41 automatisierte Tests decken den API-Client (Pagination, Rate-Limit-
Retry, Fehlerbehandlung), Normalizer, Classifier, Validator, Exporter und
den Rohdaten-Persistenz-Hook ab.

## Beispielaufruf

```bash
python -m src.cli 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
```

Mehrere Wallets in einem Lauf:

```bash
python -m src.cli 0xAdresse1... 0xAdresse2...
```

Optionale Flags: `--env-file`, `--raw-dir`, `--processed-dir`, `--log-dir`
(Defaults: `data/raw/`, `data/processed/`, `data/logs/` im Projekt-Root -
siehe `python -m src.cli --help`).

Ausgabe:
- `data/raw/<run_id>_<adresse>_<kategorie>_page<N>.json` - unveränderte
  rohe API-Antworten (Audit-Trail, Anforderung: Quelldaten nie verändern)
- `data/processed/transactions_<run_id>.csv` und `.json` - normalisierte,
  klassifizierte, validierte Transaktionen
- `data/logs/run_<run_id>.log` - API-Aufrufe, Rate-Limit-Ereignisse,
  Warnungen

### Dokumentierte Test-Adresse (Akzeptanztest)

`0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045` (`vitalik.eth`) - eine der
öffentlich am besten dokumentierten Ethereum-Adressen (ENS-verknüpft,
breit zitiert).

**Verifiziert mit einem echten Lauf (13.07.2026):** Diese Adresse ist
deutlich aktiver als "moderat" - **446.829 Transaktionen** wurden
fehlerfrei durchgängig verarbeitet (254.699 Transfer-In, 174.330
Transfer-Out, 11.939 Swap, 5.090 Contract-Interaktion, 771
Unklassifiziert). Der erste Live-Lauf hat dabei einen echten Bug
aufgedeckt: Das kostenlose Etherscan-Tier hat in der Praxis `3 req/s`
durchgesetzt (nicht die aus der Dokumentation angenommenen `5 req/s`),
und unsere Rate-Limit-Erkennung hat nur exakt auf
`"Max rate limit reached"` gematcht - die real aufgetretene Variante
`"Max calls per sec rate limit reached (3/sec)"` wurde dadurch nicht
erkannt. Dadurch wurden bereits erfolgreich abgerufene 9.000+ Datensätze
auf Seite 10 verworfen statt retryed zu werden. Behoben durch einen
breiteren Substring-Abgleich und einen konservativeren Default von
`3 req/s` (siehe `docs/adr/0002-api-choice.md` und
`src/api_client/etherscan_client.py`). Eine derart aktive Adresse ist
gerade deshalb ein guter Stresstest für Pagination und
Rate-Limit-Handling.

Für einen schnelleren Funktionstest eignet sich jede selbst gewählte
Wallet-Adresse mit weniger Transaktionen - die Anzahl lässt sich vorab
auf der Etherscan-Adressseite prüfen
(`https://etherscan.io/address/<adresse>`, Reiter "Transactions").

### Zweites Beispiel: eine kleine Wallet (schneller Vergleichslauf)

`0x7e2d0fe0ffdd78c264f8d40d19acb7d04390c6e8` - eine Gegenpartei-Adresse
aus vitalik.eths frühester (2015er) On-Chain-Historie, also eine echte,
öffentlich nachprüfbare Adresse, nur deutlich weniger aktiv.

**Verifiziert mit einem echten Lauf (13.07.2026): 26 Transaktionen**,
Laufzeit ca. 1 Sekunde (jede Kategorie passte auf eine einzige Seite,
weder Pagination noch Rate-Limiting nötig) - `9` Contract-Interaktion,
`8` Transfer-Out, `8` Unklassifiziert, `1` Transfer-In.

Auffällig ist der deutlich höhere Anteil an `Unklassifiziert` (~31 %) im
Vergleich zu vitalik.eth (~0,17 %). Das ist bewusstes, konservatives
Verhalten und kein Bug: Die meisten markierten Zeilen sind eingehende
ETH-Transfers, die zusätzlich Input-Daten auf einer "normalen"
Transaktion tragen - ein Muster, das in der frühen (2015er)
Ethereum-Nutzung häufiger vorkam. Da nicht sicher feststellbar ist, ob
ein solcher Datensatz "nur" ein Transfer ist oder etwas anderes, verweigert
der Classifier das Raten und markiert ihn stattdessen mit
`manual_review_required`. Die deutlich niedrigere Quote bei vitalik.eth
spiegelt lediglich wider, dass dort die meisten Transaktionen entweder
reine ETH-Transfers (leere Input-Daten) oder klar erkennbare Swap-Muster
sind.

Gutes Beispiel dafür, warum eine einzelne "moderate" Test-Adresse allein
nicht ausreicht, um die Klassifikationsqualität zu beurteilen -
Aktivitätsmuster unterscheiden sich stark je nach Alter und Nutzungsstil
der Wallet.

## Daten & Datenschutz (DSGVO)

Alles läuft und verbleibt lokal. `data/raw/` und `data/processed/` sind
standardmäßig in `.gitignore`, da sie wallet-bezogene Transaktionsdaten
enthalten können. Es werden keine Zugangsdaten außer dem eigenen
Etherscan-API-Key gespeichert (über `.env`, niemals committet).

## Dokumentation

- Architecture Decision Records: `docs/adr/0001-tech-stack.md`,
  `0002-api-choice.md`, `0003-output-format.md`
