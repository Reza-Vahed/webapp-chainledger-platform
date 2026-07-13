# ADR 0003: Ausgabeformat - CSV + JSON parallel

**Status:** Akzeptiert
**Datum:** 2026-07-13

## Kontext

Die Ausgabe muss laut Vorgabe sowohl menschenlesbar (Review durch
Steuerberater ohne tiefes technisches Vorwissen) als auch maschinenlesbar
(Weiterverarbeitung, späterer manueller Abgleich mit Blockpit/CoinTracking)
sein. Jede Zeile muss Transaktions-Hash, Klassifikations-Konfidenz,
Warnhinweise und Datenquelle enthalten.

## Entscheidung

Jeder Lauf erzeugt zwei Dateien mit identischem Inhalt aus derselben
kanonischen Datenstruktur, versioniert über eine `run_id` im Dateinamen
(`transactions_<run_id>.csv` / `.json`) unter `data/processed/`:

- **CSV**: flach, `warnings` als `"; "`-getrennter String, Beträge als
  Festkommastring (nicht Float).
- **JSON**: verschachtelte native Typen (`warnings` als Liste, `is_error`
  als Bool), Beträge ebenfalls als Festkommastring.

## Begründung

- CSV lässt sich direkt in Excel öffnen und in Blockpit/CoinTracking/Excel
  importieren - für den Zielnutzer (Steuerberater) der zugänglichste Weg.
- JSON bleibt verlustfrei für strukturierte Felder (Listen, Booleans) und
  eignet sich für nachgelagerte automatisierte Weiterverarbeitung/Audits.
- Beträge werden bewusst als String statt als Zahl exportiert: `Decimal`
  verliert bei JSON-Zahlen bzw. Float-Rundung Präzision, was bei
  steuerlich relevanten Beträgen inakzeptabel ist. Explizite
  Festkommaformatierung (`format(x, "f")`, nicht `str()`) verhindert
  zusätzlich, dass sehr kleine Beträge (z. B. 1 Wei) in wissenschaftliche
  Notation (`1E-18`) kippen - ein Bug, der während der Testphase gefunden
  und behoben wurde.
- Beide Dateien werden aus derselben `CanonicalTransaction`-Liste erzeugt
  (`src/exporter.py`) - kein Duplizieren der Geschäftslogik, geringer
  Mehraufwand gegenüber nur einem Format.
- Dateinamen-Versionierung über `run_id` verhindert stillschweigendes
  Überschreiben früherer Läufe (Auditierbarkeit).

## Verworfene Alternativen

- **Nur CSV:** einfachster Import, aber verschachtelte Felder (z. B.
  mehrere Warnhinweise) müssten als String kodiert werden; kein
  natives Typsystem für nachgelagerte Automatisierung.
- **Nur JSON (JSON Lines):** sauber maschinenlesbar, aber für einen
  Steuerberater ohne technisches Tool nicht direkt einsehbar/prüfbar.
- **Einzelne JSON-Datei pro Wallet statt Gesamtexport:** hätte den
  Abgleich über mehrere Wallets hinweg erschwert; ein Gesamtexport pro
  Lauf (sortiert nach Wallet, dann Zeitstempel) ist für den MVP
  ausreichend und einfacher zu prüfen.
