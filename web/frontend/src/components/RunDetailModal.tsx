import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRunDetail } from "../lib/api";
import { t } from "../lib/i18n";
import type { RunDetailCaseOut } from "../lib/types";
import SourceView from "./SourceView";
import TestCaseList from "./TestCaseList";
import VerdictBadge from "./VerdictBadge";

interface RunDetailModalProps {
  runId: number;
  problemTitle?: string;
  source?: string | null;
  onClose: () => void;
  /** summary = show only sample cases; full = show all. Default summary. */
  mode?: "summary" | "full";
  /** How many cases to show in summary mode. Default 2. */
  defaultExpandedCount?: number;
}

export default function RunDetailModal({
  runId,
  problemTitle,
  source,
  onClose,
  mode: initialMode,
  defaultExpandedCount = 2,
}: RunDetailModalProps) {
  const [mode, setMode] = useState<"summary" | "full">(initialMode ?? "summary");

  const detailQuery = useQuery({
    queryKey: ["run", "detail", runId],
    queryFn: () => getRunDetail(runId),
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const loading = detailQuery.isLoading;
  const errored = detailQuery.isError;

  const allCases = detailQuery.data?.test_cases ?? [];
  const displayCases =
    mode === "summary"
      ? allCases.filter((c: RunDetailCaseOut) => c.is_sample)
      : allCases;

  return (
    <div className="run-detail-backdrop" role="presentation">
      <div
        className="run-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("results.modal.title")}
      >
        <header className="run-detail-header">
          <h2>
            {t("results.modal.title")}
            {problemTitle !== undefined && ` — ${problemTitle}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("results.modal.close")}
          >
            ✕
          </button>
        </header>

        {loading && <p className="hint">{t("results.loading")}</p>}
        {errored && <p className="error">{t("results.loadError")}</p>}

        {detailQuery.data !== undefined && (
          <>
            <p className="run-detail-summary">
              <span className="hint">{t("results.summaryVerdict")}:</span>{" "}
              {detailQuery.data.run.summary_verdict !== null ? (
                <VerdictBadge verdict={detailQuery.data.run.summary_verdict} />
              ) : (
                <span className="hint">—</span>
              )}
              {detailQuery.data.run.status !== "done" && (
                <span className="hint">
                  {" "}({t(`results.status.${detailQuery.data.run.status}`)})
                </span>
              )}
            </p>

            {source !== undefined && source !== null && (
              <section className="run-detail-source">
                <h3>{t("submissions.code")}</h3>
                <SourceView source={source} />
              </section>
            )}

            <section className="run-detail-cases">
              <h3>
                {mode === "summary"
                  ? t("submissions.sampleCases")
                  : t("results.columns.case")}
              </h3>
              <TestCaseList
                cases={displayCases}
                limit={defaultExpandedCount}
                showAllLabel={t("submissions.showAllCases")}
              />
            </section>

            {mode === "summary" && allCases.length > displayCases.length && (
              <button
                type="button"
                className="link-button"
                onClick={() => setMode("full")}
              >
                {t("submissions.showAllCases")}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
