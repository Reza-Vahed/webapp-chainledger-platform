import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, deleteImport, listImports } from "../api/client";
import type { ImportSummary } from "../types";

// Status-Badge wiederverwendet die vorhandenen category-badge-Klassen aus
// JobProgress (siehe theme.css) statt eigener Farben - queued/running teilen
// sich die "in_progress"-Farbe (beide sind noch nicht abgeschlossen).
const STATE_BADGE_MODIFIER: Record<string, string> = {
  queued: "in_progress",
  running: "in_progress",
  done: "done",
  error: "error",
};

interface ImportHistoryProps {
  refreshSignal: number;
  onReopen: (jobId: string) => void;
  onDeleted: (jobId: string) => void;
}

export function ImportHistory({ refreshSignal, onReopen, onDeleted }: ImportHistoryProps) {
  const { t, i18n } = useTranslation();
  const dateLocaleTag = `${i18n.language}-u-ca-gregory-nu-latn`;
  const [items, setItems] = useState<ImportSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listImports()
      .then((result) => {
        if (cancelled) return;
        setItems(result.items);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof ApiError ? err.message : t("history.fetchFailed"));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t() bewusst nicht in deps: neue Sprache soll keinen Refetch ausloesen
  }, [refreshSignal]);

  async function handleDelete(jobId: string) {
    if (!window.confirm(t("history.deleteConfirm"))) return;
    setDeletingId(jobId);
    try {
      await deleteImport(jobId);
      setItems((current) => current?.filter((item) => item.job_id !== jobId) ?? current);
      onDeleted(jobId);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("history.deleteFailed"));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section className="history">
      <h2>{t("history.title")}</h2>

      {loadError && (
        <p className="form-error" role="alert">
          {loadError}
        </p>
      )}

      {items === null && !loadError && <p className="history__loading">{t("history.loading")}</p>}
      {items && items.length === 0 && <p className="history__empty">{t("history.empty")}</p>}

      {items && items.length > 0 && (
        <div className="history__table-wrapper">
          <table className="history__table">
            <thead>
              <tr>
                <th>{t("history.columnChain")}</th>
                <th>{t("history.columnAddresses")}</th>
                <th>{t("history.columnState")}</th>
                <th>{t("history.columnStarted")}</th>
                <th>{t("history.columnTotal")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.job_id}>
                  <td>{t(`chain.${item.chain}`)}</td>
                  <td>
                    <span className="history__addresses" title={item.addresses.join(", ")}>
                      {item.addresses.length > 1
                        ? `${item.addresses[0].slice(0, 10)}… (+${item.addresses.length - 1})`
                        : item.addresses[0]}
                    </span>
                  </td>
                  <td>
                    <span className={`category-badge category-badge--${STATE_BADGE_MODIFIER[item.state]}`}>
                      {t(`state.${item.state}`)}
                    </span>
                  </td>
                  <td>{new Date(item.started_at).toLocaleString(dateLocaleTag)}</td>
                  <td className="history__numeric">{item.total_transactions ?? "–"}</td>
                  <td className="history__actions">
                    <button type="button" onClick={() => onReopen(item.job_id)}>
                      {t("history.reopen")}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(item.job_id)}
                      disabled={item.state === "queued" || item.state === "running" || deletingId === item.job_id}
                    >
                      {t("history.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
