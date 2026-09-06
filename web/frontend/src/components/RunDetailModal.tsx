import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRunDetail } from "../lib/api";
import { t } from "../lib/i18n";
import type { RunDetailCaseOut } from "../lib/types";
import SourceView from "./SourceView";
import VerdictBadge from "./VerdictBadge";

interface RunDetailModalProps {
  runId: number;
  /** Shown in the modal title — problem title (looked up by the parent). */
  problemTitle?: string;
  /** Source is not exposed by /api/runs endpoints (plan API gap); if the
   *  parent has it (e.g. assignment submissions), pass it. Otherwise the
   *  source pane is hidden. */
  source?: string | null;
  onClose: () => void;
}

/**
 * Run detail modal (plan todo 31): summary verdict + per-case table with
 * verdict badge, steps, wall_ms, input, expected output (omitted for hidden
 * cases — `Oculto`), and `diff_line` for WA cases. Source renders in a
 * read-only CodeMirror pane (`pseint()`) when supplied. NEVER renders
 * `expected_output` when the server returns null (hidden cases) — that is
 * the plan MUST NOT.
 */
export default function RunDetailModal({
  runId,
  problemTitle,
  source,
  onClose,
}: RunDetailModalProps) {
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

            <RunCasesTable cases={detailQuery.data.test_cases} />

            {source !== undefined && source !== null && (
              <section className="run-detail-source">
                <h3>{t("results.source")}</h3>
                <SourceView source={source} />
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function RunCasesTable({ cases }: { cases: RunDetailCaseOut[] }) {
  if (cases.length === 0) {
    return <p className="hint">{t("results.modal.empty")}</p>;
  }
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>{t("results.columns.case")}</th>
          <th>{t("results.columns.verdict")}</th>
          <th>{t("results.columns.steps")}</th>
          <th>{t("results.columns.wall")}</th>
          <th>{t("results.columns.input")}</th>
          <th>{t("results.columns.expected")}</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr key={c.case_index}>
            <td>{c.case_index + 1}</td>
            <td>
              <VerdictBadge verdict={c.verdict} />
              {c.verdict === "WA" && c.diff_line !== null && (
                <span className="hint">
                  {" "}({t("results.diffLine")} {c.diff_line})
                </span>
              )}
            </td>
            <td>{c.steps ?? "—"}</td>
            <td>{c.wall_ms ?? "—"}</td>
            <td>
              <pre className="practice-pre">{c.input ?? "—"}</pre>
            </td>
            <td>
              {c.expected_output === null ? (
                <span className="hint">{t("results.hidden")}</span>
              ) : (
                <pre className="practice-pre">{c.expected_output}</pre>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
