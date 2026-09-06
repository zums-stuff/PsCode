import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { ProblemOut, TestCaseOut } from "../../lib/types";
import StatementEditor from "../../components/StatementEditor";
import TestCaseTable, { type TestCaseDraft } from "../../components/TestCaseTable";
import RunSampleButton from "../../components/RunSampleButton";

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
 * /admin/problems/new and /admin/problems/:id — problem form with statement
 * editor (markdown + pseint code blocks), complexity/budget/compare fields,
 * test-case table, run-sample validation, and inline validation on save.
 */
export default function AdminProblemDetail() {
  const { id } = useParams();
  const isNew = id === undefined || id === "new";
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [expectedComplexity, setExpectedComplexity] = useState("");
  const [stepBudget, setStepBudget] = useState("");
  const [compareMode, setCompareMode] = useState("exact");
  const [cases, setCases] = useState<TestCaseDraft[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const originalCasesRef = useRef<TestCaseOut[]>([]);

  const problemQuery = useQuery({
    queryKey: ["admin", "problem", id],
    queryFn: () => api.get<ProblemOut>(`/api/problems/${id}`),
    enabled: !isNew,
  });

  const casesQuery = useQuery({
    queryKey: ["admin", "problem", id, "cases"],
    queryFn: () => api.get<TestCaseOut[]>(`/api/problems/${id}/cases`),
    enabled: !isNew,
  });

  // Hydrate the form once the problem loads.
  useEffect(() => {
    const p = problemQuery.data;
    if (!p) return;
    setTitle(p.title);
    setStatement(p.statement);
    setExpectedComplexity(p.expected_complexity);
    setStepBudget(p.step_budget === null ? "" : String(p.step_budget));
    setCompareMode(p.compare_mode);
  }, [problemQuery.data]);

  // Hydrate the case table once cases load.
  useEffect(() => {
    const loaded = casesQuery.data;
    if (!loaded) return;
    originalCasesRef.current = loaded;
    setCases(
      loaded.map((c) => ({
        id: c.id,
        input: c.input,
        expected_output: c.expected_output,
        seed: c.seed,
        points: c.points,
        order: c.order,
        is_sample: c.is_sample,
      })),
    );
  }, [casesQuery.data]);

  // New problems start with one empty case row.
  useEffect(() => {
    if (isNew && cases.length === 0) setCases([emptyCase(0)]);
  }, [isNew, cases.length]);

  function validate(): string[] {
    const errs: string[] = [];
    if (!title.trim()) errs.push(t("admin.problem.validation.title"));
    if (!expectedComplexity) errs.push(t("admin.problem.validation.complexity"));
    if (cases.some((c) => !c.expected_output.trim())) {
      errs.push(t("admin.problem.validation.expectedOutput"));
    }
    return errs;
  }

  async function syncCases(problemId: number) {
    const keptIds = new Set(
      cases.filter((c) => c.id !== undefined).map((c) => c.id as number),
    );
    for (const original of originalCasesRef.current) {
      if (!keptIds.has(original.id)) {
        await api.delete(`/api/problems/${problemId}/cases/${original.id}`);
      }
    }
    for (const c of cases) {
      const payload = {
        input: c.input,
        expected_output: c.expected_output,
        seed: c.seed,
        points: c.points,
        order: c.order,
        is_sample: c.is_sample,
      };
      if (c.id !== undefined) {
        await api.patch(`/api/problems/${problemId}/cases/${c.id}`, payload);
      } else {
        await api.post(`/api/problems/${problemId}/cases`, payload);
      }
    }
  }

  async function handleSave() {
    const errs = validate();
    setErrors(errs);
    if (errs.length > 0) return;

    setSaving(true);
    setSaveError(null);
    try {
      const payload = {
        title: title.trim(),
        statement,
        expected_complexity: expectedComplexity,
        compare_mode: compareMode,
        step_budget: stepBudget === "" ? null : Number(stepBudget),
      };
      let problemId: number;
      if (isNew) {
        const created = await api.post<ProblemOut>("/api/problems", payload);
        problemId = created.id;
      } else {
        await api.patch<ProblemOut>(`/api/problems/${id}`, payload);
        problemId = Number(id);
      }
      await syncCases(problemId);
      navigate("/admin/problems");
    } catch {
      setSaveError(t("admin.problem.saveError"));
    } finally {
      setSaving(false);
    }
  }

  if (!isNew && problemQuery.isLoading) {
    return <p>{t("admin.problem.loading")}</p>;
  }

  if (!isNew && problemQuery.isError) {
    return <p className="error">{t("admin.problem.loadError")}</p>;
  }

  return (
    <div>
      <h1>{isNew ? t("admin.problem.newTitle") : t("admin.problem.title")}</h1>

      <div className="form-field">
        <label htmlFor="problem-title">{t("admin.problem.fields.title")}</label>
        <input
          id="problem-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label htmlFor="problem-statement">
          {t("admin.problem.fields.statement")}
        </label>
        <StatementEditor value={statement} onChange={setStatement} />
      </div>

      <RunSampleButton source={statement} />

      <div className="form-row">
        <div className="form-field">
          <label htmlFor="problem-complexity">
            {t("admin.problem.fields.complexity")}
          </label>
          <select
            id="problem-complexity"
            value={expectedComplexity}
            onChange={(e) => setExpectedComplexity(e.target.value)}
          >
            <option value="">{t("admin.problem.fields.complexity.empty")}</option>
            {COMPLEXITY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c === "other" ? t("complexity.other") : c}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label htmlFor="problem-step-budget">
            {t("admin.problem.fields.stepBudget")}
          </label>
          <input
            id="problem-step-budget"
            type="number"
            value={stepBudget}
            onChange={(e) => setStepBudget(e.target.value)}
            placeholder="—"
          />
        </div>

        <div className="form-field">
          <label htmlFor="problem-compare-mode">
            {t("admin.problem.fields.compareMode")}
          </label>
          <select
            id="problem-compare-mode"
            value={compareMode}
            onChange={(e) => setCompareMode(e.target.value)}
          >
            <option value="exact">{t("compareMode.exact")}</option>
            <option value="token">{t("compareMode.token")}</option>
          </select>
        </div>
      </div>

      <h2>{t("admin.problem.fields.cases")}</h2>
      {casesQuery.isError && (
        <p className="error">{t("admin.problem.casesError")}</p>
      )}
      <TestCaseTable cases={cases} onChange={setCases} />

      {errors.length > 0 && (
        <ul className="validation-errors">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}

      {saveError && <p className="error">{saveError}</p>}

      <button
        type="button"
        className="primary"
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? t("admin.problem.saving") : t("admin.problem.save")}
      </button>
    </div>
  );
}