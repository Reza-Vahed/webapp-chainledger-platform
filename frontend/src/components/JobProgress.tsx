import { useTranslation } from "react-i18next";
import type { JobStatusResponse } from "../types";

interface JobProgressProps {
  status: JobStatusResponse;
}

export function JobProgress({ status }: JobProgressProps) {
  const { t } = useTranslation();

  return (
    <section className="job-progress" aria-live="polite">
      <h2>{t("jobProgress.statusLabel", { state: t(`state.${status.state}`) })}</h2>
      <p className="job-progress__chain">{t("jobProgress.chainLabel", { chain: t(`chain.${status.chain}`) })}</p>
      {status.stage && <p className="job-progress__stage">{t("jobProgress.stageLabel", { stage: t(`stage.${status.stage}`) })}</p>}
      {status.error && (
        <p className="form-error" role="alert">
          {t("jobProgress.errorLabel", { error: status.error })}
        </p>
      )}

      {Object.values(status.addresses).map((addressProgress) => (
        <div key={addressProgress.address} className="job-progress__address">
          <h3>{addressProgress.address}</h3>
          <ul>
            {Object.values(addressProgress.categories).map((category) => (
              <li key={category.category}>
                <span className={`category-badge category-badge--${category.status}`}>
                  {t(`recordType.${category.category}`)}
                </span>{" "}
                {category.status === "error" ? (
                  <span className="form-error">{t("jobProgress.errorLabel", { error: category.error })}</span>
                ) : (
                  <span>
                    {t("jobProgress.transactionsCount", { count: category.records_fetched })} (
                    {t("jobProgress.pagesCount", { count: category.pages_fetched })})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {status.state === "done" && status.total_transactions !== null && (
        <p className="job-progress__summary">
          {t("jobProgress.summaryProcessed", { count: status.total_transactions })}
          {status.unclassified_count !== null && status.unclassified_count > 0 && (
            <> {t("jobProgress.summaryUnclassified", { count: status.unclassified_count })}</>
          )}
        </p>
      )}
    </section>
  );
}
