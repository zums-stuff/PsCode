import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { t } from "../lib/i18n";

interface SolveToolbarProps {
  problemId: number;
  source: string;
  assignmentId: string | null;
  contestId: string | null;
  onRunCreated: (runId: number) => void;
  onReset: () => void;
}

/**
 * Submit + reset + assignment/contest context banner. POST /api/runs with
 * mode practice|assignment|contest (todo 18 contract); 202 -> onRunCreated,
 * 413 (64KB cap) / 429 (quota) / other -> friendly inline notice.
 */
export default function SolveToolbar({
  problemId,
  source,
  assignmentId,
  contestId,
  onRunCreated,
  onReset,
}: SolveToolbarProps) {
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const contextLabel =
    assignmentId !== null
      ? t("solve.context.assignment").replace("{id}", assignmentId)
      : contestId !== null
        ? t("solve.context.contest").replace("{id}", contestId)
        : null;

  async function handleSubmit() {
    setSubmitting(true);
    setNotice(null);
    const mode = assignmentId !== null ? "assignment" : contestId !== null ? "contest" : "practice";
    const body: Record<string, unknown> = { problem_id: problemId, source, mode };
    if (assignmentId !== null) body.assignment_id = Number(assignmentId);
    if (contestId !== null) body.contest_id = Number(contestId);
    try {
      const res = await api.post<{ run_id: number }>("/api/runs", body);
      onRunCreated(res.run_id);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 413) setNotice(t("solve.errors.too_large"));
        else if (err.status === 429) setNotice(t("solve.errors.quota"));
        else setNotice(t("solve.errors.network"));
      } else {
        setNotice(t("solve.errors.network"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="solve-toolbar">
      {contextLabel !== null && (
        <span className="solve-context-banner">{contextLabel}</span>
      )}
      <button type="button" className="primary" onClick={handleSubmit} disabled={submitting}>
        {submitting ? t("solve.submitting") : t("solve.submit")}
      </button>
      <button type="button" onClick={onReset}>
        {t("solve.reset")}
      </button>
      {notice !== null && <span className="solve-notice">{notice}</span>}
    </div>
  );
}