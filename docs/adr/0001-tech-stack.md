# ADR 0001: Tech-Stack (Python 3.11+, requests, pydantic, pytest)

**Status:** Akzeptiert
**Datum:** 2026-07-13

## Kontext

Der Datenimport-Agent ist ein CLI-Tool ohne UI/DB, das öffentliche On-Chain-Daten
abruft, normalisiert, klassifiziert und als Datei exportiert. Ergebnis muss von
Steuerberatern ohne tiefes technisches Vorwissen nachvollziehbar sein, und der
Code dient als Referenzprojekt für ein B2B-Consulting-Angebot - Lesbarkeit und
Nachvollziehbarkeit wiegen daher stärker als Performance.

## Entscheidung

- **Sprache:** Python 3.11+
- **HTTP:** `requests` (synchron, keine Async-Bibliothek)
- **Konfiguration:** `python-dotenv` für `.env`-basierte API-Keys
- **Kanonisches Datenmodell:** `pydantic` (v2) statt Standardlib-`dataclasses`
- **Tests:** `pytest`
- Keine Datenbank, kein Web-Framework, kein Pandas

## Begründung

- Python bietet die beste Balance aus Lesbarkeit und schnellem CLI-Setup; keine
  Web3-/ABI-Dekodier-Bibliotheken nötig, da ausschließlich REST-JSON gelesen wird.
- `pydantic` validiert das kanonische Transaktionsmodell zur Laufzeit (Typen,
  Wertebereiche wie `confidence ∈ [0,1]`) und liefert damit robustere Garantien
  als reine `dataclasses` - wichtig, da das Modell die zentrale, auditierbare
  Schnittstelle zwischen Normalizer, Classifier, Validator und Exporter ist.
- Synchrones `requests` genügt, da Abrufe ohnehin durch das Etherscan-Rate-Limit
  sequenziell gedrosselt werden - Async brächte hier keinen echten Vorteil.
- Keine DB/UI/Pandas, um dem MVP-Fokus treu zu bleiben (keine Abhängigkeiten,
  die nicht direkt zur Kernaufgabe beitragen).

## Verworfene Alternativen

- **Node.js/TypeScript:** gleichwertig möglich, aber mehr Boilerplate für ein
  Ein-Personen-CLI-Tool dieser Größe.
- **dataclasses (Standardlib):** kein eingebautes Validierungsverhalten; bei
  fehlerhaften/unerwarteten API-Werten würde die Struktur stillschweigend
  falsche Typen akzeptieren statt früh und explizit zu scheitern.
- **Pandas:** unnötig für lineare Transaktionslisten ohne komplexe Aggregation
  im MVP-Scope; zusätzliche schwere Abhängigkeit ohne klaren Mehrwert.
- **aiohttp/asyncio:** kein Nutzen bei ohnehin sequenziell gedrosselten
  Aufrufen; erhöht nur Komplexität.
