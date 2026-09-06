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

/**
 * Practice sandbox output (plan todo 30): per-case rows with verdict badge,
 * input/output/expected, steps and wall_ms. TLE over the step budget shows a
 * suggested fix; CE shows the compiler error. Never grades.
 */
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
        <p className="hint">{t("solve.practice.empty")}</p>
      </section>
    );
  }

  return (
    <section className="solve-results">
      <h2>{t("solve.practice.title")}</h2>
      {run.test_results.length === 0 ? (
        <p className="hint">{t("solve.results.status." + run.status)}</p>
      ) : (
        <table className="data-table">
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
              const expected = testCases[tr.case_index]?.expected_output ?? "—";
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
                  <td>
                    <pre className="practice-pre">{stdin}</pre>
                  </td>
                  <td>
                    <pre className="practice-pre">{tr.output ?? "—"}</pre>
                  </td>
                  <td>
                    <pre className="practice-pre">{expected}</pre>
                  </td>
                  <td>{tr.steps ?? "—"}</td>
                  <td>{tr.wall_ms ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
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