import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type { ContestProblem, Page, ProblemListItem, ProblemOut } from "../lib/types";
import PhaseAwareActions from "./PhaseAwareActions";
import StatementEditor from "./StatementEditor";
import TestCaseTable, { type TestCaseDraft } from "./TestCaseTable";

const COMPLEXITY_OPTIONS = [
  "O(1)",
  "O(log n)",
  "O(n)",
  "O(n log n)",
  "O(n²)",
  "O(n³)",
  "O(2ⁿ)",
  "other",
] as const;

function emptyCase(order: number): TestCaseDraft {
  return {
    input: "",
    expected_output: "",
    seed: 0,
    points: 1,
    order,
    is_sample: false,
  };
}

/**
 * Contest problem-set editor: list ordered problems, add from the problemset
 * OR create a fresh problem for this contest, remove, and reorder (PATCH).
 * Wrapped in PhaseAwareActions so reorder/remove are disabled before the
 * contest starts.
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

  const [tab, setTab] = useState<"existing" | "new">("existing");

  // New-problem form state
  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [expectedComplexity, setExpectedComplexity] = useState("");
  const [compareMode, setCompareMode] = useState("exact");
  const [stepBudget, setStepBudget] = useState("");
  const [cases, setCases] = useState<TestCaseDraft[]>([emptyCase(0)]);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

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

  async function handleCreate() {
    if (!title.trim() || !expectedComplexity) return;
    setCreateError(null);
    setCreating(true);
    try {
      const created = await api.post<ProblemOut>("/api/problems", {
        title: title.trim(),
        statement,
        expected_complexity: expectedComplexity,
        compare_mode: compareMode,
        step_budget: stepBudget === "" ? null : Number(stepBudget),
        is_public: false,
      });
      for (const c of cases) {
        await api.post(`/api/problems/${created.id}/cases`, {
          input: c.input,
          expected_output: c.expected_output,
          seed: c.seed,
          points: c.points,
          order: c.order,
          is_sample: c.is_sample,
        });
      }
      await api.post(`/api/contests/${contestId}/contest-problems`, {
        problem_id: created.id,
      });
      // Reset the create form
      setTitle("");
      setStatement("");
      setExpectedComplexity("");
      setCompareMode("exact");
      setStepBudget("");
      setCases([emptyCase(0)]);
      setTab("existing");
      onChanged();
    } catch {
      setCreateError(t("admin.contests.problems.new.error"));
    } finally {
      setCreating(false);
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

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "existing"}
          onClick={() => setTab("existing")}
        >
          {t("admin.contests.problems.tab.existing")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "new"}
          onClick={() => setTab("new")}
        >
          {t("admin.contests.problems.tab.new")}
        </button>
      </div>

      {tab === "existing" && (
        <PhaseAwareActions phase={phase}>
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
            <button
              type="button"
              className="primary"
              onClick={handleAdd}
              disabled={!problemId}
            >
              {t("admin.contests.problems.add")}
            </button>
          </div>
        </PhaseAwareActions>
      )}

      {tab === "new" && (
        <PhaseAwareActions phase={phase}>
          <div className="new-problem-form">
            <div className="form-field">
              <label htmlFor="new-problem-title">
                {t("admin.problem.fields.title")}
              </label>
              <input
                id="new-problem-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="form-field">
              <label htmlFor="new-problem-statement">
                {t("admin.problem.fields.statement")}
              </label>
              <StatementEditor value={statement} onChange={setStatement} />
            </div>

            <div className="form-row">
              <div className="form-field">
                <label htmlFor="new-problem-complexity">
                  {t("admin.problem.fields.complexity")}
                </label>
                <select
                  id="new-problem-complexity"
                  value={expectedComplexity}
                  onChange={(e) => setExpectedComplexity(e.target.value)}
                >
                  <option value="">
                    {t("admin.problem.fields.complexity.empty")}
                  </option>
                  {COMPLEXITY_OPTIONS.map((c) => (
                    <option key={c} value={c}>
                      {c === "other" ? t("complexity.other") : c}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-field">
                <label htmlFor="new-problem-compare-mode">
                  {t("admin.problem.fields.compareMode")}
                </label>
                <select
                  id="new-problem-compare-mode"
                  value={compareMode}
                  onChange={(e) => setCompareMode(e.target.value)}
                >
                  <option value="exact">{t("compareMode.exact")}</option>
                  <option value="token">{t("compareMode.token")}</option>
                </select>
              </div>

              <div className="form-field">
                <label htmlFor="new-problem-step-budget">
                  {t("admin.problem.fields.stepBudget")}
                </label>
                <input
                  id="new-problem-step-budget"
                  type="number"
                  value={stepBudget}
                  onChange={(e) => setStepBudget(e.target.value)}
                  placeholder="—"
                />
              </div>
            </div>

            <h3>{t("admin.problem.fields.cases")}</h3>
            <TestCaseTable cases={cases} onChange={setCases} />

            <p className="hint">
              {t("admin.contests.problems.new.hint")}
            </p>

            {createError && <p className="error">{createError}</p>}

            <button
              type="button"
              className="primary"
              onClick={handleCreate}
              disabled={creating || !title.trim() || !expectedComplexity}
            >
              {creating
                ? t("admin.contests.problems.new.creating")
                : t("admin.contests.problems.new.submit")}
            </button>
          </div>
        </PhaseAwareActions>
      )}
    </div>
  );
}
