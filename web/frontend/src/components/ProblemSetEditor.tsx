import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type { ContestProblem, Page, ProblemListItem } from "../lib/types";
import PhaseAwareActions from "./PhaseAwareActions";

/**
 * Contest problem-set editor: list ordered problems, add from the problemset,
 * remove, and reorder via up/down arrows (PATCH order). Wrapped in
 * PhaseAwareActions so reorder/remove are disabled before the contest starts.
 */
export default function ProblemSetEditor({
  contestId,
  phase,
  problems,
  onChanged,
}: {
  contestId: number;
  phase: string;
  problems: ContestProblem[];
  onChanged: () => void;
}) {
  const [problemId, setProblemId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState<ProblemListItem[]>([]);

  async function loadAvailable() {
    try {
      const page = await api.get<Page<ProblemListItem>>(
        "/api/problems?page=1&size=100",
      );
      setAvailable(page.items);
    } catch {
      setAvailable([]);
    }
  }

  async function handleAdd() {
    if (!problemId) return;
    setError(null);
    try {
      await api.post(`/api/contests/${contestId}/contest-problems`, {
        problem_id: Number(problemId),
      });
      setProblemId("");
      onChanged();
    } catch {
      setError(t("admin.contests.problems.addError"));
    }
  }

  async function handleRemove(pid: number) {
    setError(null);
    try {
      await api.delete(`/api/contests/${contestId}/contest-problems/${pid}`);
      onChanged();
    } catch {
      setError(t("admin.contests.problems.removeError"));
    }
  }

  async function handleMove(index: number, dir: -1 | 1) {
    const target = index + dir;
    if (target < 0 || target >= problems.length) return;
    setError(null);
    const current = problems[index];
    const other = problems[target];
    try {
      await api.patch(`/api/contests/${contestId}/contest-problems/${current.problem_id}`, {
        order: other.order,
      });
      await api.patch(`/api/contests/${contestId}/contest-problems/${other.problem_id}`, {
        order: current.order,
      });
      onChanged();
    } catch {
      setError(t("admin.contests.problems.reorderError"));
    }
  }

  const usedIds = new Set(problems.map((p) => p.problem_id));
  const addable = available.filter((p) => !usedIds.has(p.id));

  return (
    <div>
      {problems.length === 0 && <p>{t("admin.contests.problems.empty")}</p>}
      {problems.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("admin.contests.columns.id")}</th>
              <th>{t("admin.contests.columns.title")}</th>
              <th>{t("admin.contests.problems.reorder")}</th>
              <th>{t("admin.contests.columns.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {problems.map((p, i) => (
              <tr key={p.problem_id}>
                <td>{p.problem_id}</td>
                <td>{p.title}</td>
                <td>
                  <PhaseAwareActions phase={phase}>
                    <button
                      type="button"
                      aria-label={`${t("admin.contests.problems.reorder")} ↑`}
                      onClick={() => handleMove(i, -1)}
                      disabled={i === 0}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={`${t("admin.contests.problems.reorder")} ↓`}
                      onClick={() => handleMove(i, 1)}
                      disabled={i === problems.length - 1}
                    >
                      ↓
                    </button>
                  </PhaseAwareActions>
                </td>
                <td>
                  <PhaseAwareActions phase={phase}>
                    <button
                      type="button"
                      className="danger"
                      onClick={() => handleRemove(p.problem_id)}
                    >
                      {t("admin.contests.problems.remove")}
                    </button>
                  </PhaseAwareActions>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {error && <p className="error">{error}</p>}
      <div className="form-row">
        <select
          value={problemId}
          onChange={(e) => setProblemId(e.target.value)}
          onFocus={loadAvailable}
        >
          <option value="">{t("admin.contests.problems.select")}</option>
          {addable.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
        <PhaseAwareActions phase={phase}>
          <button
            type="button"
            className="primary"
            onClick={handleAdd}
            disabled={!problemId}
          >
            {t("admin.contests.problems.add")}
          </button>
        </PhaseAwareActions>
      </div>
    </div>
  );
}
