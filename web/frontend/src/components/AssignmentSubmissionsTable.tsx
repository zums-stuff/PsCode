import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type { AssignmentSubmissionOut } from "../lib/types";
import SourceView from "./SourceView";

interface Props {
  assignmentId: number;
  problemId: number;
  rows: AssignmentSubmissionOut[];
  onRejudged: () => void;
}

/** Per-student best submissions for an assignment, with source + rejudge. */
export default function AssignmentSubmissionsTable({
  assignmentId,
  problemId,
  rows,
  onRejudged,
}: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [rejudging, setRejudging] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (rows.length === 0) {
    return <p>{t("admin.assignments.empty")}</p>;
  }

  async function handleRejudge(row: AssignmentSubmissionOut) {
    setRejudging(row.user_id);
    setError(null);
    try {
      await api.post("/api/runs", {
        problem_id: problemId,
        source: row.source,
        mode: "assignment",
        assignment_id: assignmentId,
      });
      onRejudged();
    } catch {
      setError(t("admin.assignments.rejudgeError"));
    } finally {
      setRejudging(null);
    }
  }

  return (
    <div>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>{t("admin.assignments.columns.student")}</th>
            <th>{t("admin.assignments.columns.verdict")}</th>
            <th>{t("admin.assignments.columns.steps")}</th>
            <th>{t("admin.assignments.columns.source")}</th>
            <th>{t("admin.assignments.columns.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.user_id}>
              <td>{row.username}</td>
              <td>{row.best_verdict ?? "—"}</td>
              <td>{row.steps ?? "—"}</td>
              <td>
                <button
                  type="button"
                  onClick={() =>
                    setExpanded(expanded === row.user_id ? null : row.user_id)
                  }
                >
                  {expanded === row.user_id
                    ? t("admin.assignments.source.hide")
                    : t("admin.assignments.source.view")}
                </button>
              </td>
              <td>
                <button
                  type="button"
                  onClick={() => handleRejudge(row)}
                  disabled={rejudging === row.user_id}
                >
                  {rejudging === row.user_id
                    ? t("admin.assignments.rejudging")
                    : t("admin.assignments.rejudge")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {expanded !== null && (
        <SourceView
          source={rows.find((r) => r.user_id === expanded)?.source ?? ""}
        />
      )}
    </div>
  );
}