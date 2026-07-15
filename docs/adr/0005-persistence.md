# ADR 0005: Persistente Speicherung der Import-Historie - SQLite (Metadaten) + bestehende JSON-Exporte

**Status:** Akzeptiert
**Datum:** 2026-07-15

## Kontext

Bis Phase 3 lebte der Job-Status (`api/jobs.py::Job`) ausschließlich im
Prozess-Speicher des FastAPI-Backends - dokumentierte MVP-Grenze
(README: "job state lives in the backend process's memory only").
Abgeschlossene Importe (`data/processed/transactions_<job_id>.csv/.json`)
überlebten zwar bereits einen Neustart als Dateien, waren aber ohne die
zugehörigen Job-Metadaten (welche Adresse, welche Chain, wann, wie viele
Treffer) über die Web-API nicht mehr auffindbar oder erneut aufrufbar.
Phase 3 verlangt: abgeschlossene Importe müssen einen Seiten-Reload UND
einen Backend-Neustart überstehen, das Frontend muss eine Liste
vergangener Importe mit Wiederöffnen-Möglichkeit zeigen, und gespeicherte
Ergebnisse müssen manuell löschbar sein (keine unbegrenzte automatische
Aufbewahrung).

## Entscheidung

**SQLite** (`api/db.py`, Python-Standardbibliothek `sqlite3`) für die
Job-**Metadaten** (`jobs`-Tabelle: id, chain, addresses, state, error,
started_at, finished_at, total_transactions, unclassified_count,
csv_path, json_path). Die validierten Transaktionen selbst werden
**nicht** noch einmal in der Datenbank gespeichert - sie liegen bereits
vollständig und unverändert in `data/processed/transactions_<job_id>.json`
(existierender Exporter-Output, siehe ADR 0003). Beim Wiederöffnen eines
abgeschlossenen Jobs nach einem Neustart wird diese Datei zurückgelesen
und direkt in `CanonicalTransaction`-Objekte deserialisiert
(`api/jobs.py::_load_job_from_store`).

## Begründung

| | SQLite (nur Metadaten) | Datei-basiert (JSON-Manifest je Job + Index-Datei) |
|---|---|---|
| Neue Abhängigkeit | Keine (Standardbibliothek) | Keine |
| Nebenläufigkeit | Robust - jeder Job läuft bereits in einem eigenen Hintergrund-Thread (bestehendes Pattern), SQLite regelt Schreibzugriffe selbst (WAL-Modus) | Eine gemeinsame Index-Datei ist ein Read-Modify-Write-Hotspot bei parallelen Jobs - eigenes Locking nötig, fehleranfällig |
| Historie: Filtern/Sortieren | Native SQL-Abfrage (`ORDER BY started_at DESC`) | Muss vollständig in Anwendungscode nachgebaut werden |
| Einzelnen Eintrag löschen | Eine `DELETE`-Anweisung | Gesamte Index-Datei neu schreiben |
| Datenduplizierung | Keine - Transaktionsdaten bleiben ausschließlich in der bereits vorhandenen JSON-Exportdatei | Würde ohne zusätzliche Überlegung ebenfalls duplizieren, wenn Transaktionsdaten mit gespeichert würden |

SQLite gewinnt vor allem wegen der bereits bestehenden Multi-Thread-Job-
Ausführung: jeder Job-Thread schreibt bei Statuswechseln
(queued → running → done/error) einen Snapshot in die DB
("Write-Through"), während der FastAPI-Event-Loop parallel alle 1,5s
Status-Polling-Anfragen bedient. Eine geteilte JSON-Index-Datei hätte
dafür eigenes Datei-Locking erfordert - SQLite übernimmt das nativ.

Bewusst **keine** Duplizierung der Transaktionsdaten in der DB: Ein
Job wie `vitalik.eth` auf Mainnet erzeugt 446.829 Zeilen - diese
zusätzlich in SQLite zu spiegeln hätte den Speicherbedarf verdoppelt,
ohne neuen Nutzen (die JSON-Exportdatei ist als Audit-Artefakt bereits
die maßgebliche, unveränderliche Quelle). Die DB bleibt dadurch klein
und schnell, unabhängig vom Transaktionsvolumen einzelner Jobs.

## Konsequenzen für Aufbewahrung/Löschung

- Neuer Endpunkt `DELETE /api/v1/imports/{job_id}` entfernt DB-Zeile,
  zugehörige `data/raw/*`- und `data/processed/transactions_<id>.*`-
  Dateien. Laufende Jobs (`queued`/`running`) können nicht gelöscht
  werden (409), um Races mit dem aktiv schreibenden Job-Thread zu
  vermeiden.
- Bewusst **kein** automatischer Ablauf-/Retention-Mechanismus (z. B.
  ein `--max-age-days`-Flag mit Hintergrund-Scheduler) - das wäre für
  ein Einzelnutzer-Demo-Tool ohne Nutzerkonten Over-Engineering und
  würde einen Scheduler/Cron-Prozess erfordern, den die Vorgabe explizit
  ausschließt. Manuelles Löschen aus der Historie ist der Mindeststandard
  laut Vorgabe und wird vollständig erfüllt.
- Neue DB-Datei (`data/chainledger.db` inkl. `-wal`/`-shm`-Begleitdateien
  im WAL-Modus) ist in `.gitignore` aufgenommen, da sie wallet-bezogene
  Job-Historie enthält (DSGVO-Konsistenz mit `data/raw/`, `data/processed/`).

## Migration bestehender In-Memory-Jobs

Kein Migrationsschritt für Jobs, die zum Zeitpunkt des Deployments
bereits im Prozess-Speicher liefen - ein sauberer Neustart genügt
(gleiches Verhalten wie bisher bei jedem Neustart/Deploy, da vor Phase 3
ohnehin kein Job einen Neustart überlebte). Es existieren keine
Produktivnutzer, deren laufende Jobs beim Rollout verloren gehen könnten.

## Verifikation

Gegen einen echten, mit `kill -9` beendeten und neu gestarteten
Backend-Prozess getestet (nicht nur simuliert durch Leeren des
In-Memory-Caches innerhalb desselben Prozesses): Job-Status, Historie
(`GET /api/v1/imports`) und Transaktionsabruf blieben nach dem Neustart
korrekt abrufbar, `DELETE` funktionierte gegen den laufenden Prozess
und entfernte die zugehörigen Dateien.

## Verworfene Alternativen

- **Datei-basiert (JSON-Manifest + Index):** siehe Vergleichstabelle
  oben - vor allem wegen fehlender nativer Nebenläufigkeitskontrolle
  verworfen.
- **Externer DB-Server (PostgreSQL o. ä.):** deutlich mehr
  Betriebsaufwand (eigener Prozess/Container) für ein
  Einzelnutzer-Tool ohne Multi-Worker-Anforderung - klar
  Over-Engineering, von der Vorgabe explizit ausgeschlossen.
- **ORM (z. B. SQLAlchemy) über rohem `sqlite3`:** Das Schema besteht
  aus einer einzigen, kleinen Tabelle mit einfachen CRUD-Operationen -
  ein ORM hätte eine weitere Abhängigkeit und Abstraktionsschicht ohne
  proportionalen Nutzen eingeführt.
