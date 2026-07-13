import type { JobStatusResponse } from "../types";

const STAGE_LABELS: Record<string, string> = {
  fetching: "Daten werden abgerufen",
  classifying: "Klassifizierung läuft",
  validating: "Validierung läuft",
  exporting: "Export wird erstellt",
};

const STATE_LABELS: Record<string, string> = {
  queued: "In Warteschlange",
  running: "Läuft",
  done: "Abgeschlossen",
  error: "Fehler",
};

const CATEGORY_LABELS: Record<string, string> = {
  normal: "Normale Transaktionen",
  internal: "Interne Transfers",
  erc20: "ERC-20 Token-Transfers",
};

interface JobProgressProps {
  status: JobStatusResponse;
}

export function JobProgress({ status }: JobProgressProps) {
  return (
    <section className="job-progress" aria-live="polite">
      <h2>Status: {STATE_LABELS[status.state] ?? status.state}</h2>
      {status.stage && <p className="job-progress__stage">Phase: {STAGE_LABELS[status.stage] ?? status.stage}</p>}
      {status.error && (
        <p className="form-error" role="alert">
          Fehler: {status.error}
        </p>
      )}

      {Object.values(status.addresses).map((addressProgress) => (
        <div key={addressProgress.address} className="job-progress__address">
          <h3>{addressProgress.address}</h3>
          <ul>
            {Object.values(addressProgress.categories).map((category) => (
              <li key={category.category}>
                <span className={`category-badge category-badge--${category.status}`}>
                  {CATEGORY_LABELS[category.category] ?? category.category}
                </span>{" "}
                {category.status === "error" ? (
                  <span className="form-error">Fehler: {category.error}</span>
                ) : (
                  <span>
                    {category.records_fetched} Transaktionen ({category.pages_fetched}{" "}
                    {category.pages_fetched === 1 ? "Seite" : "Seiten"})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {status.state === "done" && status.total_transactions !== null && (
        <p className="job-progress__summary">
          Fertig: {status.total_transactions} Transaktionen verarbeitet
          {status.unclassified_count !== null && status.unclassified_count > 0 && (
            <> – {status.unclassified_count} davon unklassifiziert (manuelle Prüfung empfohlen)</>
          )}
          .
        </p>
      )}
    </section>
  );
}
