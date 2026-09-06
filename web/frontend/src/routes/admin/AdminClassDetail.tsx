import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueries, useQueryClient } from "@tanstack/react-query";
import { api, getAssignmentSubmissions } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import type {
  AssignmentListItem,
  ClassOut,
  Page,
  ProblemListItem,
} from "../../lib/types";
import ClassCodeDisplay from "../../components/ClassCodeDisplay";
import MemberList from "../../components/MemberList";

/**
 * /admin/classes/new (create form, admin only) and /admin/classes/:id
 * (rename, join code, members, assignments). Teachers may only open their
 * own classes — anyone else is redirected to /403.
 */
export default function AdminClassDetail() {
  const { id } = useParams();
  const isNew = id === undefined || id === "new";
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const classesQuery = useQuery({
    queryKey: ["admin", "classes"],
    queryFn: () => api.get<ClassOut[]>("/api/classes"),
    enabled: !isNew,
  });

  const cls = classesQuery.data?.find((c) => c.id === Number(id));

  const assignmentsQuery = useQuery({
    queryKey: ["admin", "assignments"],
    queryFn: () =>
      api.get<Page<AssignmentListItem>>("/api/assignments?page=1&size=100"),
    enabled: !isNew && cls !== undefined,
  });

  const problemsQuery = useQuery({
    queryKey: ["admin", "problems"],
    queryFn: () =>
      api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
    enabled: !isNew && cls !== undefined,
  });

  const problemTitles = new Map(
    (problemsQuery.data?.items ?? []).map((p) => [p.id, p.title]),
  );

  const submissionCounts = useQueries({
    queries: (assignmentsQuery.data?.items ?? []).map((a) => ({
      queryKey: ["admin", "assignment", a.id, "submissions"],
      queryFn: () => getAssignmentSubmissions(a.id),
      enabled: !isNew && cls !== undefined,
    })),
  });

  if (!isNew && classesQuery.isLoading) {
    return <p>{t("admin.classes.loading")}</p>;
  }

  if (!isNew && classesQuery.isError) {
    return <p className="error">{t("admin.classes.error")}</p>;
  }

  if (!isNew && cls === undefined) {
    return <p className="error">{t("admin.classes.notFound")}</p>;
  }

  if (
    !isNew &&
    user?.role === "teacher" &&
    cls !== undefined &&
    cls.teacher_id !== user.id
  ) {
    return <Navigate to="/403" replace />;
  }

  async function handleSave() {
    if (isNew) {
      if (user?.role !== "admin") {
        setSaveError(t("admin.classes.new.teacherOnly"));
        return;
      }
      setSaving(true);
      setSaveError(null);
      try {
        const created = await api.post<ClassOut>("/api/classes", {
          name: name.trim(),
        });
        navigate(`/admin/classes/${created.id}`);
      } catch {
        setSaveError(t("admin.classes.new.error"));
      } finally {
        setSaving(false);
      }
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      await api.patch<ClassOut>(`/api/classes/${id}`, { name: name.trim() });
      await queryClient.invalidateQueries({ queryKey: ["admin", "classes"] });
    } catch {
      setSaveError(t("admin.classes.edit.error"));
    } finally {
      setSaving(false);
    }
  }

  if (isNew) {
    return (
      <div>
        <h1>{t("admin.classes.newTitle")}</h1>
        {user?.role !== "admin" && (
          <p className="error">{t("admin.classes.new.teacherOnly")}</p>
        )}
        <div className="form-field">
          <label htmlFor="class-name">{t("admin.classes.new.name")}</label>
          <input
            id="class-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        {saveError && <p className="error">{saveError}</p>}
        <button
          type="button"
          className="primary"
          onClick={handleSave}
          disabled={saving || user?.role !== "admin"}
        >
          {saving ? t("admin.classes.new.creating") : t("admin.classes.new.create")}
        </button>
      </div>
    );
  }

  return (
    <div>
      <h1>{cls?.name}</h1>

      <div className="form-field">
        <label htmlFor="class-name">{t("admin.classes.edit.name")}</label>
        <input
          id="class-name"
          type="text"
          value={name || cls?.name || ""}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      {saveError && <p className="error">{saveError}</p>}
      <button
        type="button"
        className="primary"
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? t("admin.classes.edit.saving") : t("admin.classes.edit.save")}
      </button>

      <h2>{t("admin.classes.columns.code")}</h2>
      {cls && <ClassCodeDisplay code={cls.code} />}

      <h2>{t("admin.classes.members")}</h2>
      <MemberList members={[]} />

      <h2>{t("admin.classes.assignments")}</h2>
      <div className="admin-page-header">
        <Link className="primary" to={`/admin/classes/${id}/assignments/new`}>
          {t("admin.assignments.new")}
        </Link>
      </div>
      {assignmentsQuery.isLoading && <p>{t("admin.assignments.loading")}</p>}
      {assignmentsQuery.isError && (
        <p className="error">{t("admin.assignments.loadError")}</p>
      )}
      {assignmentsQuery.data && assignmentsQuery.data.items.length === 0 && (
        <p>{t("admin.assignments.empty")}</p>
      )}
      {assignmentsQuery.data && assignmentsQuery.data.items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("admin.assignments.columns.deadline")}</th>
              <th>{t("admin.assignments.problem")}</th>
              <th>{t("admin.assignments.columns.submissions")}</th>
              <th>{t("admin.assignments.columns.verdict")}</th>
            </tr>
          </thead>
          <tbody>
            {assignmentsQuery.data.items.map((a, i) => {
              const count = submissionCounts[i]?.data?.length;
              return (
                <tr key={a.id}>
                  <td>{new Date(a.deadline).toLocaleString()}</td>
                  <td>{problemTitles.get(a.problem_id) ?? `#${a.problem_id}`}</td>
                  <td>{count ?? "—"}</td>
                  <td>
                    {a.status === "open"
                      ? t("admin.assignments.status.open")
                      : t("admin.assignments.status.closed")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}