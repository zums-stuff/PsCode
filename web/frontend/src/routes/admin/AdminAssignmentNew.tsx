import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { Page, ProblemListItem } from "../../lib/types";

/** /admin/classes/:id/assignments/new — pick a problem + deadline. */
export default function AdminAssignmentNew() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [problemId, setProblemId] = useState("");
  const [deadline, setDeadline] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const problemsQuery = useQuery({
    queryKey: ["admin", "problems"],
    queryFn: () =>
      api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
  });

  async function handleCreate() {
    if (!problemId || !deadline) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.post("/api/assignments", {
        class_id: Number(id),
        problem_id: Number(problemId),
        deadline: new Date(deadline).toISOString(),
      });
      navigate(`/admin/classes/${id}`);
    } catch {
      setSaveError(t("admin.assignments.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1>{t("admin.assignments.newTitle")}</h1>

      {problemsQuery.isLoading && <p>{t("admin.assignments.loading")}</p>}
      {problemsQuery.isError && (
        <p className="error">{t("admin.assignments.loadError")}</p>
      )}

      {problemsQuery.data && (
        <div className="form-field">
          <label htmlFor="assignment-problem">{t("admin.assignments.problem")}</label>
          <select
            id="assignment-problem"
            value={problemId}
            onChange={(e) => setProblemId(e.target.value)}
          >
            <option value="">—</option>
            {problemsQuery.data.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="form-field">
        <label htmlFor="assignment-deadline">
          {t("admin.assignments.deadline")}
        </label>
        <input
          id="assignment-deadline"
          type="datetime-local"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
        />
      </div>

      {saveError && <p className="error">{saveError}</p>}

      <button
        type="button"
        className="primary"
        onClick={handleCreate}
        disabled={saving || !problemId || !deadline}
      >
        {saving ? t("admin.assignments.creating") : t("admin.assignments.create")}
      </button>
    </div>
  );
}