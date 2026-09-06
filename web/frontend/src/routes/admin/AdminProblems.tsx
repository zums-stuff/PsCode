import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import type { Page, ProblemListItem } from "../../lib/types";

/** /admin/problems — paginated problem list with per-user solved state. */
export default function AdminProblems() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin", "problems"],
    queryFn: () => api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
  });

  async function handleDelete(id: number) {
    if (!window.confirm(t("admin.problems.deleteConfirm"))) return;
    setDeleteError(null);
    try {
      await api.delete(`/api/problems/${id}`);
      await queryClient.invalidateQueries({ queryKey: ["admin", "problems"] });
    } catch {
      setDeleteError(t("admin.problems.deleteError"));
    }
  }

  function solvedLabel(row: ProblemListItem): string {
    if (user?.role === "admin") return t("admin.problems.solved.na");
    return row.is_solved
      ? t("admin.problems.solved.yes")
      : t("admin.problems.solved.no");
  }

  return (
    <div>
      <div className="admin-page-header">
        <h1>{t("admin.problems.title")}</h1>
        <Link className="primary" to="/admin/problems/new">
          {t("admin.problems.new")}
        </Link>
      </div>

      {isLoading && <p>{t("admin.problems.loading")}</p>}

      {isError && (
        <div>
          <p className="error">{t("admin.problems.error")}</p>
          <button type="button" onClick={() => refetch()}>
            {t("admin.problems.retry")}
          </button>
        </div>
      )}

      {deleteError && <p className="error">{deleteError}</p>}

      {data && data.items.length === 0 && <p>{t("admin.problems.empty")}</p>}

      {data && data.items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("admin.problems.columns.id")}</th>
              <th>{t("admin.problems.columns.title")}</th>
              <th>{t("admin.problems.columns.complexity")}</th>
              <th>{t("admin.problems.columns.solved")}</th>
              <th>{t("admin.problems.columns.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>{row.title}</td>
                <td>{row.expected_complexity}</td>
                <td>{solvedLabel(row)}</td>
                <td>
                  <Link to={`/admin/problems/${row.id}`}>
                    {t("admin.problems.edit")}
                  </Link>{" "}
                  <button
                    type="button"
                    className="danger"
                    onClick={() => handleDelete(row.id)}
                  >
                    {t("admin.problems.delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}