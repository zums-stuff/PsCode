import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { ClassOut } from "../../lib/types";
import ClassCodeDisplay from "../../components/ClassCodeDisplay";

/** /admin/classes — class list with join codes, open links, delete. */
export default function AdminClasses() {
  const queryClient = useQueryClient();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin", "classes"],
    queryFn: () => api.get<ClassOut[]>("/api/classes"),
  });

  async function handleDelete(id: number) {
    if (!window.confirm(t("admin.classes.deleteConfirm"))) return;
    setDeleteError(null);
    try {
      await api.delete(`/api/classes/${id}`);
      await queryClient.invalidateQueries({ queryKey: ["admin", "classes"] });
    } catch {
      setDeleteError(t("admin.classes.deleteError"));
    }
  }

  return (
    <div>
      <div className="admin-page-header">
        <h1>{t("admin.classes.title")}</h1>
        <Link className="primary" to="/admin/classes/new">
          {t("admin.classes.new")}
        </Link>
      </div>

      {isLoading && <p>{t("admin.classes.loading")}</p>}

      {isError && (
        <div>
          <p className="error">{t("admin.classes.error")}</p>
          <button type="button" onClick={() => refetch()}>
            {t("admin.classes.retry")}
          </button>
        </div>
      )}

      {deleteError && <p className="error">{deleteError}</p>}

      {data && data.length === 0 && <p>{t("admin.classes.empty")}</p>}

      {data && data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("admin.classes.columns.id")}</th>
              <th>{t("admin.classes.columns.name")}</th>
              <th>{t("admin.classes.columns.code")}</th>
              <th>{t("admin.classes.columns.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((cls) => (
              <tr key={cls.id}>
                <td>{cls.id}</td>
                <td>{cls.name}</td>
                <td>
                  <ClassCodeDisplay code={cls.code} />
                </td>
                <td>
                  <Link to={`/admin/classes/${cls.id}`}>
                    {t("admin.classes.open")}
                  </Link>{" "}
                  <button
                    type="button"
                    className="danger"
                    onClick={() => handleDelete(cls.id)}
                  >
                    {t("admin.classes.delete")}
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