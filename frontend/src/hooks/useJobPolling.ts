// Pollt den Job-Status alle POLL_INTERVAL_MS, solange der Job laeuft.
// Bewusste Entscheidung (siehe Phase-2-Planung): Polling statt SSE/WebSocket
// - einfachste robuste Loesung fuer ein MVP ohne zusaetzliche Infrastruktur.

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, getImportStatus } from "../api/client";
import type { JobStatusResponse } from "../types";

const POLL_INTERVAL_MS = 1500;

interface UseJobPollingResult {
  status: JobStatusResponse | null;
  pollError: string | null;
}

export function useJobPolling(jobId: string | null): UseJobPollingResult {
  const { t } = useTranslation();
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setStatus(null);
    setPollError(null);

    if (!jobId) {
      return;
    }

    let cancelled = false;

    async function poll(): Promise<void> {
      try {
        const result = await getImportStatus(jobId as string);
        if (cancelled) return;
        setStatus(result);
        setPollError(null);
        if (result.state === "running" || result.state === "queued") {
          timerRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : t("errors.statusFetchFailed");
        setPollError(message);
      }
    }

    void poll();

    return () => {
      cancelled = true;
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t() bewusst nicht in deps: neue Sprache soll laufendes Polling nicht neu starten
  }, [jobId]);

  return { status, pollError };
}
