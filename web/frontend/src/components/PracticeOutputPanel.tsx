import { t } from "../lib/i18n";
import type { RunDetailOut, TestCaseOut } from "../lib/types";

interface PracticeOutputPanelProps {
  run: RunDetailOut | null;
  testCases: TestCaseOut[];
  stdin: string;
  stepBudget: number | null;
}

function verdictClass(verdict: string): string {
  switch (verdict) {
    case "AC":
      return "status-green";
    case "WA":
      return "status-red";
    case "TLE":
      return "status-yellow";
    case "RE":
      return "status-orange";
    case "CE":
      return "status-purple";
    default:
      return "status-gray";
  }
}

export default function PracticeOutputPanel({
  run,
  testCases,
  stdin,
  stepBudget,
}: PracticeOutputPanelProps) {
  if (run === null) {
    return (
      <section className="solve-results">
        <h2>{t("solve.practice.title")}</h2>
        <p className="hint">{t("student.practice.outputPlaceholder")}</p>
      </section>
    );
  }

  return (
    <section className="solve-results">
      <h2>{t("solve.practice.title")}</h2>
      {run.test_results.length === 0 ? (
        <p className="hint">{t("solve.results.status." + run.status)}</p>
      ) : (
        <>
          <table className="datatable">
            <thead>
              <tr>
                <th>{t("solve.results.case")}</th>
                <th>{t("solve.results.verdict")}</th>
                <th>{t("solve.practice.input")}</th>
                <th>{t("solve.practice.output")}</th>
                <th>{t("solve.practice.expected")}</th>
                <th>{t("solve.results.steps")}</th>
                <th>{t("solve.results.wall")}</th>
              </tr>
            </thead>
            <tbody>
              {run.test_results.map((tr) => {
                const tc = testCases[tr.case_index];
                const caseInput = tc?.input ?? stdin;
                const expected = tc?.expected_output ?? "—";
                const overBudget =
                  tr.verdict === "TLE" &&
                  stepBudget !== null &&
                  (tr.steps ?? 0) > stepBudget;
                return (
                  <tr key={tr.id}>
                    <td>{tr.case_index + 1}</td>
                    <td>
                      <span className={`status-badge ${verdictClass(tr.verdict)}`}>
                        {tr.verdict}
                      </span>
                    </td>
                    <td style={{ textAlign: "left" }}>
                      <pre className="practice-pre">{caseInput}</pre>
                    </td>
                    <td style={{ textAlign: "left" }}>
                      <pre className="practice-pre">{tr.output ?? "—"}</pre>
                    </td>
                    <td style={{ textAlign: "left" }}>
                      <pre className="practice-pre">{expected}</pre>
                    </td>
                    <td>{tr.steps ?? "—"}</td>
                    <td>{tr.wall_ms ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {run.test_results
            .filter((tr) => tr.verdict === "WA" && tr.output !== null)
            .map((tr) => {
              const tc = testCases[tr.case_index];
              const expected = tc?.expected_output ?? null;
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
        </>
      )}
      {run.test_results.some(
        (tr) =>
          tr.verdict === "TLE" &&
          stepBudget !== null &&
          (tr.steps ?? 0) > stepBudget,
      ) && <p className="solve-notice">{t("solve.practice.tle_suggestion")}</p>}
      {run.test_results
        .filter((tr) => tr.verdict === "CE" && tr.error !== null)
        .map((tr) => (
          <div key={tr.id}>
            <p className="solve-notice">{t("solve.practice.ce_error")}</p>
            <pre className="practice-pre practice-error">{tr.error}</pre>
          </div>
        ))}
    </section>
  );
}