import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import { useToast } from "../../lib/toast";
import { useConfirm } from "../../lib/confirm";
import type { ClassOut } from "../../lib/types";
import ClassCodeDisplay from "../../components/ClassCodeDisplay";

export default function AdminClasses() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin", "classes"],
    queryFn: () => api.get<ClassOut[]>("/api/classes"),
  });

  async function handleDelete(id: number) {
    const ok = await confirm({
      title: t("admin.classes.delete"),
      message: t("admin.classes.deleteConfirm"),
      confirmLabel: t("admin.classes.delete"),
      variant: "danger",
    });
    if (!ok) return;
    try {
      await api.delete(`/api/classes/${id}`);
      toast.success(t("admin.classes.deleted"));
      await queryClient.invalidateQueries({ queryKey: ["admin", "classes"] });
    } catch {
      toast.error(t("admin.classes.deleteError"));
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

      {data && data.length === 0 && <p>{t("admin.classes.empty")}</p>}

      {data && data.length > 0 && (
        <table className="datatable">
          <thead>
            <tr>
              <th>{t("admin.classes.columns.id")}</th>
              <th style={{ textAlign: "left" }}>{t("admin.classes.columns.name")}</th>
              <th style={{ textAlign: "left" }}>{t("admin.classes.columns.code")}</th>
              <th>{t("admin.classes.columns.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((cls) => (
              <tr key={cls.id}>
                <td>{cls.id}</td>
                <td style={{ textAlign: "left" }}>{cls.name}</td>
                <td style={{ textAlign: "left" }}>
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