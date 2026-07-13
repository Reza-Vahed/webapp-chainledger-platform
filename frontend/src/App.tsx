import { useState } from "react";
import { AddressForm } from "./components/AddressForm";
import { JobProgress } from "./components/JobProgress";
import { ResultsTable } from "./components/ResultsTable";
import { ThemeToggle } from "./components/ThemeToggle";
import { ApiError, createImport } from "./api/client";
import { useJobPolling } from "./hooks/useJobPolling";

function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { status, pollError } = useJobPolling(jobId);

  const isRunning = status?.state === "queued" || status?.state === "running";

  async function handleSubmit(address: string) {
    setSubmitError(null);
    try {
      const created = await createImport([address]);
      setJobId(created.job_id);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Import konnte nicht gestartet werden.");
    }
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>ChainLedger Platform</h1>
        <ThemeToggle />
      </header>

      <main>
        <AddressForm onSubmit={handleSubmit} disabled={isRunning} />
        {submitError && (
          <p className="form-error" role="alert">
            {submitError}
          </p>
        )}
        {pollError && (
          <p className="form-error" role="alert">
            {pollError}
          </p>
        )}
        {status && <JobProgress status={status} />}
        {status?.state === "done" && <ResultsTable jobId={status.job_id} />}
      </main>
    </div>
  );
}

export default App;
