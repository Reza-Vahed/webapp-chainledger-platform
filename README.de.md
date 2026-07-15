# ChainLedger Platform - On-Chain-Datenimport-Agent (MVP)

[![GitHub release](https://img.shields.io/github/v/release/Reza-Vahed/webapp-chainledger-platform)](https://github.com/Reza-Vahed/webapp-chainledger-platform/releases/tag/v3.0.0)

🇬🇧 [English version](README.md)

Ein strikt read-only CLI- + Web-Tool, das On-Chain-Transaktionsdaten
direkt von öffentlichen EVM-Wallet-Adressen (Ethereum Mainnet, Arbitrum
One) abruft, in ein kanonisches Modell normalisiert, nach einer festen
steuerlich relevanten Kategorienliste klassifiziert, offensichtliche
Datenprobleme markiert und als CSV + JSON für den manuellen Abgleich mit
Krypto-Steuer-Tools (z. B. Blockpit, CoinTracking) exportiert.

Dies ist ein Portfolio-/technisches Validierungsprojekt, **keine**
Steuersoftware.

## Was dieses Tool NICHT tut

- Keine Nutzerkonten/Auth, kein externer DB-Server, keine
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

### Multi-Chain-Support

Aktuell werden zwei Chains unterstützt: **Ethereum Mainnet** (Default)
und **Arbitrum One**, wählbar über `--chain` (CLI) bzw. das
Chain-Dropdown (Web-UI). Beide werden über **denselben**
`EtherscanClient` bedient, parametrisiert über eine kleine
Chain-Registry (`src/api_client/chains.py`) - Etherscan API V2 deckt
beide Chains (und 50+ weitere EVM-Chains) über denselben Endpunkt und
API-Key ab, es war also keine zweite Client-Implementierung und kein
zusätzlicher API-Key nötig. Die Klassifikationslogik bleibt unverändert
chain-übergreifend identisch; nur das native Gas-Token-Symbol/-Decimals
und die Allowlists bekannter Contracts (`src/classifier.py`) sind
chain-geschlüsselt, damit eine Mainnet-Contract-Adresse nie fälschlich
für einen unabhängigen Contract auf einer anderen Chain gehalten wird.
Der vollständige Vergleich (Arbitrum vs. Polygon) sowie die
Live-Rate-Limit-Verifikation stehen in
`docs/adr/0004-multi-chain-support.md`.

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

81 automatisierte Tests decken den API-Client (Pagination, Rate-Limit-
Retry, Fehlerbehandlung), Normalizer, Classifier, Validator, Exporter,
den Rohdaten-Persistenz-Hook, die Chain-Registry sowie den
SQLite-basierten Job-Store (`api/db.py`) ab.

## Beispielaufruf

```bash
python -m src.cli 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
```

Dieselbe Wallet auf Arbitrum One statt Ethereum Mainnet:

```bash
python -m src.cli 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --chain arbitrum
```

Mehrere Wallets in einem Lauf:

```bash
python -m src.cli 0xAdresse1... 0xAdresse2...
```

Optionale Flags: `--chain` (Default `ethereum`, alternativ `arbitrum`),
`--env-file`, `--raw-dir`, `--processed-dir`, `--log-dir` (Defaults:
`data/raw/`, `data/processed/`, `data/logs/` im Projekt-Root - siehe
`python -m src.cli --help`).

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

### Akzeptanztest Arbitrum One (dieselben Adressen, andere Chain)

EOA-Adressen sind chain-übergreifend identisch, daher wurden beide obigen
Adressen mit einem echten Lauf gegen **Arbitrum One** (`--chain arbitrum`)
erneut verifiziert, statt neue Referenzadressen zu suchen.

**`vitalik.eth`, verifiziert mit einem echten Lauf (15.07.2026): 20.070
Transaktionen**, durchgängig verarbeitet in ca. 11 Sekunden (20.038
Transfer-In, 10 Swap, 3 Contract-Interaktion, 2 Transfer-Out, 17
Unklassifiziert). Deutlich geringeres Volumen als auf Mainnet (dort
446.829) - konsistent damit, dass diese Adresse deutlich stärker
Mainnet-nativ ist - aber immer noch genug, um Pagination real zu testen:
Sowohl `normal` als auch `tokentx` erreichten Etherscans
10.000-Datensätze-Pagination-Fenster und lösten eine
`startblock`-Verschiebung aus (`src/api_client/etherscan_client.py`) -
bestätigt, dass dieser Mechanismus unverändert auch auf einer zweiten
Chain funktioniert. In diesem sequenziellen CLI-Lauf waren keine
Rate-Limit-Retries nötig.

**Kleine Wallet `0x7e2d0fe0ffdd78c264f8d40d19acb7d04390c6e8`, verifiziert
mit einem echten Lauf (15.07.2026): 7 Transaktionen** (6
Contract-Interaktion, 1 Unklassifiziert) - Laufzeit ca. 1 Sekunde, jede
Kategorie passte auf eine einzige Seite, weder Pagination noch
Rate-Limiting nötig.

## Web-Frontend (Phase 2 + 3)

Eine React+TypeScript-SPA (`frontend/`) sitzt auf einem schlanken
FastAPI-Wrapper (`api/`) um dieselbe oben beschriebene Pipeline auf - keine
doppelte Logik, CLI und Web-App teilen sich unverändert `src/`.

- **Dreisprachige UI** (Deutsch/Englisch/Farsi) mit Sprachumschalter,
  Default: Deutsch. Farsi wird rechts-nach-links dargestellt (`dir="rtl"`),
  inklusive gespiegelter Tabellenspalten und richtungsgerechter
  Pagination-Pfeile. Daten werden in allen Sprachen konsequent im
  gregorianischen Kalender mit westlichen Ziffern angezeigt (erzwungen
  über eine Unicode-Locale-Extension) - ohne das würde der Browser bei
  "fa" automatisch auf den persischen Kalender und persische Ziffern
  umschalten, was beim Abgleich mit den CSV/JSON-Exporten (immer
  gregorianisch) verwirrend wäre.
- Light/Dark-Theme-Umschalter (persistiert in `localStorage`).
- Wallet-Adresse eingeben, Chain (Ethereum Mainnet oder Arbitrum One) im
  Dropdown wählen, Live-Fortschritt pro Kategorie beobachten (Polling
  alle 1,5 s - bewusst statt SSE/WebSocket als einfachste robuste
  MVP-Lösung gewählt), danach Ergebnisse in einer paginierten,
  filterbaren, sortierbaren Tabelle mit CSV-/JSON-Download durchsuchen.
- **Import-Historie**: Liste vergangener Importe (jede Chain, jeder
  Status) mit der Möglichkeit, ein abgeschlossenes Ergebnis erneut zu
  öffnen oder zu löschen (entfernt DB-Zeile sowie zugehörige
  Roh-/Export-Dateien; blockiert bei laufenden Jobs). Übersteht
  Backend-Neustarts - siehe "Persistenz" unten.
- Der Etherscan-API-Key erreicht nie den Browser - nur das FastAPI-Backend
  spricht mit Etherscan, über dieselbe `.env` wie die CLI.

### Backend-Setup

```bash
source .venv/bin/activate               # im Projekt-Root
pip install -r requirements-dev.txt     # enthält fastapi, uvicorn, httpx
uvicorn api.main:app --reload --port 8000
```

### Frontend-Setup

```bash
cd frontend
npm install
cp .env.example .env    # VITE_API_BASE_URL, Default http://localhost:8000
npm run dev
```

Dann http://localhost:5173/ öffnen. Beide Server müssen gleichzeitig
laufen (zwei getrennte Prozesse in diesem MVP - noch kein kombinierter
Start-Befehl und noch kein Docker-Packaging, `api/` und `frontend/` sind
aber bewusst als getrennte Verzeichnisse/Prozesse angelegt, damit das
später eine kleine Ergänzung statt eines Umbaus ist).

### API-Endpunkte (Backend)

| Methode & Pfad | Zweck |
|---|---|
| `POST /api/v1/imports` | Startet Job für 1+ Adressen (`chain`: Default `ethereum` oder `arbitrum`) |
| `GET /api/v1/imports` | Import-Historie (alle Chains, alle Status), neueste zuerst |
| `GET /api/v1/imports/{id}` | Job-Status + Fortschritt pro Kategorie (fürs Polling) |
| `GET /api/v1/imports/{id}/transactions` | Paginierte/gefilterte/sortierte Ergebnisse |
| `GET /api/v1/imports/{id}/export/{csv,json}` | Download des erzeugten Exports |
| `DELETE /api/v1/imports/{id}` | Löscht einen abgeschlossenen/fehlgeschlagenen Import (`409` bei laufendem Job) |

### Persistenz

Job-Metadaten (Chain, Adressen, Status, Zeitstempel, Zähler) werden bei
jedem Statusübergang in eine lokale SQLite-Datenbank
(`data/chainledger.db`, in `.gitignore`) geschrieben. Die validierten
Transaktionen selbst werden **nicht** zusätzlich in der Datenbank
gespeichert - sie liegen bereits in
`data/processed/transactions_<job_id>.json` (siehe "Ausgabe" oben) und
werden beim Wiederöffnen eines abgeschlossenen Imports nach einem
Neustart von dort zurückgelesen. Verifiziert gegen einen echten,
per `kill` beendeten und neu gestarteten Backend-Prozess, nicht nur
simuliert - der vollständige Vergleich mit einer datei-basierten
Alternative sowie die Begründung stehen in
`docs/adr/0005-persistence.md`.

Die Aufbewahrung ist bewusst nur manuell steuerbar: abgeschlossene
Importe bleiben bestehen, bis sie explizit über API/UI gelöscht werden -
kein automatischer Ablauf, kein Hintergrund-Scheduler (wäre für ein
Einzelnutzer-Tool Over-Engineering). Das Löschen eines laufenden Jobs
wird abgelehnt (`409`), um Races mit dessen schreibendem Thread zu
vermeiden.

Bekannte verbleibende MVP-Grenze (dokumentiert, nicht gelöst): Ein
einzelner Prozess hält die aktuell laufenden Jobs im Speicher (kein
Multi-Worker-Support), und ein Job, der beim Absturz des Backends gerade
"running" war, bleibt in der Historie danach dauerhaft auf "running"
stehen (keine Recovery-Heuristik). Für ein Einzelnutzer-Demo-Tool ohne
Nutzerkonten ausreichend.

### Backend-Tests

```bash
pytest tests/test_api_imports.py tests/test_cli.py tests/test_job_store.py tests/test_chains.py -v
```

Nutzt FastAPIs `TestClient` mit einem Fake-Etherscan-Client - keine
echten Netzwerkaufrufe, kein API-Key zum Ausführen nötig.

## Daten & Datenschutz (DSGVO)

Alles läuft und verbleibt lokal. `data/raw/`, `data/processed/` und die
Job-Historie-Datenbank (`data/chainledger.db`) sind standardmäßig in
`.gitignore`, da sie wallet-bezogene Transaktionsdaten enthalten können.
Es werden keine Zugangsdaten außer dem eigenen Etherscan-API-Key
gespeichert (über `.env`, niemals committet) - das gilt identisch für
CLI und Web-Backend, die dieselbe `.env`-Datei lesen. Derselbe Key deckt
jede unterstützte Chain ab (siehe "Multi-Chain-Support" oben), Arbitrum
führt also kein neues Secret ein. Die Import-Historie bleibt bestehen,
bis sie manuell gelöscht wird (siehe "Persistenz" oben) - bewusst keine
automatische unbegrenzte Aufbewahrung.

## Dokumentation

- Architecture Decision Records: `docs/adr/0001-tech-stack.md`,
  `0002-api-choice.md`, `0003-output-format.md`,
  `0004-multi-chain-support.md`, `0005-persistence.md`
