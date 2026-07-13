import { useEffect, useState } from "react";
import { ApiError, exportUrl, getImportTransactions } from "../api/client";
import type { TransactionsPage } from "../types";

// Feste Kategorienliste (siehe src/models.py::TxCategory) - Farbzuordnung
// per fester Reihenfolge (Slot 1-7 der validierten Dataviz-Palette,
// niemals rotiert), siehe theme.css .category-pill--slot-*.
const CATEGORY_SLOT: Record<string, number> = {
  "Transfer-In": 1,
  "Transfer-Out": 2,
  Swap: 3,
  "Staking-Reward": 4,
  Airdrop: 5,
  "Contract-Interaktion": 6,
  Unklassifiziert: 7,
};
const CATEGORIES = Object.keys(CATEGORY_SLOT);

const SORTABLE_COLUMNS: { key: string; label: string }[] = [
  { key: "timestamp", label: "Zeitstempel" },
  { key: "category", label: "Kategorie" },
  { key: "amount", label: "Betrag" },
  { key: "confidence", label: "Confidence" },
  { key: "block_number", label: "Block" },
];

const PAGE_SIZE = 25;

interface ResultsTableProps {
  jobId: string;
}

export function ResultsTable({ jobId }: ResultsTableProps) {
  const [category, setCategory] = useState("");
  const [minConfidence, setMinConfidence] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("timestamp");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const [data, setData] = useState<TransactionsPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Filter-/Sortieraenderung => zurueck auf Seite 1.
  useEffect(() => {
    setPage(1);
  }, [category, minConfidence, search, sort, order]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getImportTransactions(jobId, {
      category: category || undefined,
      minConfidence: minConfidence === "" ? undefined : Number(minConfidence),
      search: search || undefined,
      sort,
      order,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof ApiError ? err.message : "Transaktionen konnten nicht geladen werden.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, category, minConfidence, search, sort, order, page]);

  function toggleSort(key: string) {
    if (sort === key) {
      setOrder((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setOrder("asc");
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <section className="results">
      <div className="results__toolbar">
        <div className="results__filters">
          <label>
            Kategorie
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">Alle</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label>
            Min. Confidence
            <input
              type="number"
              min={0}
              max={1}
              step={0.1}
              value={minConfidence}
              onChange={(event) => setMinConfidence(event.target.value)}
              placeholder="0.0"
            />
          </label>
          <label>
            Suche (Hash/Adresse)
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="0x…"
              spellCheck={false}
            />
          </label>
        </div>

        <div className="results__downloads">
          <a href={exportUrl(jobId, "csv")} download className="results__download-link">
            CSV herunterladen
          </a>
          <a href={exportUrl(jobId, "json")} download className="results__download-link">
            JSON herunterladen
          </a>
        </div>
      </div>

      {loadError && (
        <p className="form-error" role="alert">
          {loadError}
        </p>
      )}

      <div className="results__table-wrapper">
        <table className="results__table">
          <thead>
            <tr>
              {SORTABLE_COLUMNS.map((col) => (
                <th key={col.key}>
                  <button type="button" className="results__sort-button" onClick={() => toggleSort(col.key)}>
                    {col.label}
                    {sort === col.key ? (order === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                </th>
              ))}
              <th>Richtung</th>
              <th>Token</th>
              <th>TX-Hash</th>
              <th>Warnhinweise</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((tx, index) => (
              <tr key={`${tx.tx_hash}-${tx.record_type}-${tx.token_symbol}-${tx.direction}-${index}`}>
                <td>{new Date(tx.timestamp).toLocaleString("de-DE")}</td>
                <td>
                  <span className={`category-pill category-pill--slot-${CATEGORY_SLOT[tx.category] ?? 7}`}>
                    {tx.category}
                  </span>
                </td>
                <td className="results__numeric">{tx.amount}</td>
                <td className="results__numeric">{tx.confidence.toFixed(2)}</td>
                <td className="results__numeric">{tx.block_number}</td>
                <td>{tx.direction === "in" ? "Eingang" : "Ausgang"}</td>
                <td>{tx.token_symbol}</td>
                <td>
                  <span className="results__hash" title={tx.tx_hash}>
                    {tx.tx_hash.slice(0, 10)}…
                  </span>
                </td>
                <td>
                  {tx.warnings.length > 0 ? (
                    <span className="results__warning" title={tx.warnings.join(" | ")}>
                      ⚠ {tx.warnings.length}
                    </span>
                  ) : (
                    "–"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <p className="results__loading">Lädt…</p>}
        {data && data.items.length === 0 && !loading && <p className="results__empty">Keine Treffer für diese Filter.</p>}
      </div>

      {data && (
        <div className="results__pagination">
          <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
            ← Zurück
          </button>
          <span>
            Seite {page} von {totalPages} ({data.total} Treffer)
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
          >
            Weiter →
          </button>
        </div>
      )}
    </section>
  );
}
