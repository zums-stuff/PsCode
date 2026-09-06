import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { ContestListItem, Page } from "../../lib/types";
import ContestStatusBadge from "../../components/ContestStatusBadge";

/** /admin/contests — contest list with status badge, scoring, teams, actions. */
export default function AdminContests() {
  const queryClient = useQueryClient();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin", "contests"],
    queryFn: () => api.get<Page<ContestListItem>>("/api/contests?page=1&size=100"),
  });

  async function handleDelete(id: number) {
    if (!window.confirm(t("admin.contests.deleteConfirm"))) return;
    setDeleteError(null);
    try {
      await api.delete(`/api/contests/${id}`);
      await queryClient.invalidateQueries({ queryKey: ["admin", "contests"] });
    } catch {
      setDeleteError(t("admin.contests.deleteError"));
    }
  }

  const items = data?.items ?? [];

  return (
    <div>
      <div className="admin-page-header">
        <h1>{t("admin.contests.title")}</h1>
        <Link className="primary" to="/admin/contests/new">
          {t("admin.contests.new")}
        </Link>
      </div>

      {isLoading && <p>{t("admin.contests.loading")}</p>}

      {isError && (
        <div>
          <p className="error">{t("admin.contests.error")}</p>
          <button type="button" onClick={() => refetch()}>
            {t("admin.contests.retry")}
          </button>
        </div>
      )}

      {deleteError && <p className="error">{deleteError}</p>}

      {!isLoading && !isError && items.length === 0 && (
        <p>{t("admin.contests.empty")}</p>
      )}

      {items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("admin.contests.columns.id")}</th>
              <th>{t("admin.contests.columns.title")}</th>
              <th>{t("admin.contests.columns.start")}</th>
              <th>{t("admin.contests.columns.end")}</th>
              <th>{t("admin.contests.columns.status")}</th>
              <th>{t("admin.contests.columns.scoring")}</th>
              <th>{t("admin.contests.columns.teams")}</th>
              <th>{t("admin.contests.columns.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((contest) => (
              <tr key={contest.id}>
                <td>{contest.id}</td>
                <td>{contest.title}</td>
                <td>{new Date(contest.start_at).toLocaleString()}</td>
                <td>{new Date(contest.end_at).toLocaleString()}</td>
                <td>
                  <ContestStatusBadge
                    startAt={contest.start_at}
                    endAt={contest.end_at}
                  />
                </td>
                <td>
                  {contest.scoring_mode === "cf"
                    ? t("admin.contests.scoring.cf")
                    : t("admin.contests.scoring.ioi")}
                </td>
                <td>
                  {contest.teams_enabled
                    ? t("admin.contests.teams.yes")
                    : t("admin.contests.teams.no")}
                </td>
                <td>
                  <Link to={`/admin/contests/${contest.id}`}>
                    {t("admin.contests.open")}
                  </Link>{" "}
                  <button
                    type="button"
                    className="danger"
                    onClick={() => handleDelete(contest.id)}
                  >
                    {t("admin.contests.delete")}
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
