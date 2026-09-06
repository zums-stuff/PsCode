import type { RunDetailOut } from "../lib/types";
import { t } from "../lib/i18n";

function statusClass(status: string): string {
  if (status === "done") return "status-green";
  if (status === "failed") return "status-red";
  return "status-gray";
}

/** Results pane: empty state until a run exists, then status + per-case table. */
export default function SolveResultsPane({ run }: { run: RunDetailOut | null }) {
  return (
    <section className="solve-results">
      <h2>{t("solve.results.title")}</h2>
      {run === null ? (
        <p className="hint">{t("solve.results.empty")}</p>
      ) : (
        <>
          <p>
            <span className={`status-badge ${statusClass(run.status)}`}>
              {t(`solve.results.status.${run.status}`)}
            </span>
            {run.summary_verdict !== null && (
              <span className="status-badge status-green">{run.summary_verdict}</span>
            )}
          </p>
          {run.test_results.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("solve.results.case")}</th>
                  <th>{t("solve.results.verdict")}</th>
                  <th>{t("solve.results.steps")}</th>
                  <th>{t("solve.results.wall")}</th>
                </tr>
              </thead>
              <tbody>
                {run.test_results.map((tr) => (
                  <tr key={tr.id}>
                    <td>{tr.case_index + 1}</td>
                    <td>
                      <span className={`status-badge ${statusClass(tr.verdict)}`}>
                        {tr.verdict}
                      </span>
                    </td>
                    <td>{tr.steps ?? "—"}</td>
                    <td>{tr.wall_ms ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}