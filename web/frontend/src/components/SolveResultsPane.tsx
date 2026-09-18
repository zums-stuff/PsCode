import type { RunDetailOut, TestCaseOut } from "../lib/types";
import { t } from "../lib/i18n";

function statusClass(status: string): string {
  if (status === "done") return "status-green";
  if (status === "failed") return "status-red";
  return "status-gray";
}

function verdictIcon(verdict: string): string {
  switch (verdict) {
    case "AC":
      return "✓";
    case "WA":
      return "✕";
    case "TLE":
      return "⏱";
    case "RE":
      return "⚠";
    case "CE":
      return "⚙";
    default:
      return "…";
  }
}

function verdictClass(verdict: string): string {
  switch (verdict) {
    case "AC":
      return "case-indicator--pass";
    case "WA":
      return "case-indicator--fail";
    case "TLE":
      return "case-indicator--tle";
    case "RE":
      return "case-indicator--re";
    case "CE":
      return "case-indicator--ce";
    default:
      return "case-indicator--pending";
  }
}

interface SolveResultsPaneProps {
  run: RunDetailOut | null;
  testCases?: TestCaseOut[];
}

export default function SolveResultsPane({
  run,
  testCases = [],
}: SolveResultsPaneProps) {
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
              <span className="status-badge status-green">
                {run.summary_verdict}
              </span>
            )}
          </p>

          {run.status !== "done" && run.status !== "failed" && (
            <div className="solve-results-progress">
              <p className="hint">{t("solve.results.running")}</p>
              <div className="case-indicators">
                {testCases.map((tc, idx) => {
                  const result = run.test_results.find(
                    (tr) => tr.case_index === idx,
                  );
                  return (
                    <span
                      key={tc.id}
                      className={`case-indicator ${
                        result ? verdictClass(result.verdict) : "case-indicator--pending"
                      }`}
                      title={`${t("solve.results.caseProgress")
                        .replace("{index}", String(idx + 1))
                        .replace("{status}", result ? result.verdict : t("solve.results.pending"))}`}
                    >
                      {result ? verdictIcon(result.verdict) : idx + 1}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {run.test_results.length > 0 && (
            <div className="solve-results-cases">
              <table className="datatable">
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
                        <span
                          className={`case-indicator-inline ${verdictClass(tr.verdict)}`}
                        >
                          {verdictIcon(tr.verdict)} {tr.verdict}
                        </span>
                      </td>
                      <td>{tr.steps ?? "—"}</td>
                      <td>{tr.wall_ms ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {run.test_results
                .filter((tr) => tr.verdict === "WA" && tr.output !== null)
                .map((tr) => {
                  const expected =
                    testCases[tr.case_index]?.expected_output ?? null;
                  return (
                    <div key={tr.id} className="diff-view">
                      <h4>
                        {t("solve.results.diff.title").replace(
                          "{index}",
                          String(tr.case_index + 1),
                        )}
                      </h4>
                      <div className="diff-columns">
                        <div className="diff-column diff-column--actual">
                          <strong>{t("solve.results.diff.actual")}</strong>
                          <pre className="diff-pre">{tr.output}</pre>
                        </div>
                        {expected !== null && (
                          <div className="diff-column diff-column--expected">
                            <strong>{t("solve.results.diff.expected")}</strong>
                            <pre className="diff-pre">{expected}</pre>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </>
      )}
    </section>
  );
}
