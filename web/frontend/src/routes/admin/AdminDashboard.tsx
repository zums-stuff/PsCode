/**
 * /admin — overview / landing page (plan todo 26).
 *
 * Role-aware summary for teacher/admin: open assignments with submission
 * counts, upcoming/running contests, recent student submissions, plus the
 * global flagged-pair count (sidebar badge).  This page is a navigation
 * + summary surface only — every section is a Link to the corresponding
 * admin subpage, NEVER a duplicate of its full page logic.
 *
 * Role visibility is implicit:
 * - `/api/assignments`, `/api/contests`, `/api/classes` all scope their
 *   server-side response to the caller's role (admin: all, teacher: own
 *   classes / all contests).  The dashboard just renders what it gets.
 * - The anticheat badge sums flagged pairs across every class the caller
 *   may see; `/api/admin/anticheat` itself enforces ownership.
 */

import { Link, Navigate } from "react-router-dom";
import { useQuery, useQueries } from "@tanstack/react-query";
import { api, getAssignmentSubmissions } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import type {
  AnticheatPair,
  AssignmentListItem,
  AssignmentSubmissionOut,
  ClassOut,
  ContestListItem,
  Page,
  ProblemListItem,
} from "../../lib/types";
import ContestStatusBadge from "../../components/ContestStatusBadge";
import VerdictBadge from "../../components/VerdictBadge";

const RECENT_LIMIT = 5;
const ANTICHEAT_THRESHOLD = 0.85;

function formatDeadline(deadline: string): string {
  const date = new Date(deadline);
  return Number.isNaN(date.getTime()) ? deadline : date.toLocaleString();
}

export default function AdminDashboard() {
  const { user } = useAuth();

  if (user?.role === "student") {
    return <Navigate to="/403" replace />;
  }

  const assignmentsQuery = useQuery({
    queryKey: ["admin", "dashboard", "assignments"],
    queryFn: () =>
      api.get<Page<AssignmentListItem>>(
        "/api/assignments?page=1&size=100",
      ),
  });

  const problemsQuery = useQuery({
    queryKey: ["admin", "dashboard", "problems"],
    queryFn: () =>
      api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
  });

  const contestsQuery = useQuery({
    queryKey: ["admin", "dashboard", "contests"],
    queryFn: () =>
      api.get<Page<ContestListItem>>("/api/contests?page=1&size=100"),
  });

  const classesQuery = useQuery({
    queryKey: ["admin", "dashboard", "classes"],
    queryFn: () => api.get<ClassOut[]>("/api/classes"),
  });

  const anticheatQueries = useQueries({
    queries: (classesQuery.data ?? []).map((cls) => ({
      queryKey: ["admin", "dashboard", "anticheat", cls.id] as const,
      queryFn: () =>
        api.get<AnticheatPair[]>(
          `/api/admin/anticheat?scope=class&scope_id=${cls.id}&threshold=${ANTICHEAT_THRESHOLD}`,
        ),
      enabled: classesQuery.isSuccess,
    })),
  });

  const recentSubmissionQueries = useQueries({
    queries: ((assignmentsQuery.data?.items ?? [])
      .filter((a) => a.status === "open")
      .slice(0, RECENT_LIMIT) as AssignmentListItem[]).map((a) => ({
      queryKey: [
        "admin",
        "dashboard",
        "assignment",
        a.id,
        "submissions",
      ] as const,
      queryFn: () => getAssignmentSubmissions(a.id),
      enabled: assignmentsQuery.isSuccess,
    })),
  });

  const allQueries = [
    assignmentsQuery,
    problemsQuery,
    contestsQuery,
    classesQuery,
  ];
  const loading = allQueries.some((q) => q.isLoading);
  const error = allQueries.find((q) => q.isError);

  const problemTitles = new Map(
    (problemsQuery.data?.items ?? []).map((p) => [p.id, p.title]),
  );

  const openAssignments = (assignmentsQuery.data?.items ?? []).filter(
    (a) => a.status === "open",
  );

  const activeContests = (contestsQuery.data?.items ?? []).filter(
    (c) => c.status === "upcoming" || c.status === "running",
  );

  const flaggedPairCount = anticheatQueries.reduce(
    (sum, q) => sum + (q.data?.length ?? 0),
    0,
  );

  const recentSubmissions: {
    assignmentId: number;
    row: AssignmentSubmissionOut;
  }[] = [];
  const openSorted = (assignmentsQuery.data?.items ?? [])
    .filter((a) => a.status === "open")
    .slice(0, RECENT_LIMIT);
  openSorted.forEach((a, i) => {
    const sub = recentSubmissionQueries[i]?.data ?? [];
    for (const row of sub) {
      recentSubmissions.push({ assignmentId: a.id, row });
    }
  });
  recentSubmissions.sort((a, b) => b.assignmentId - a.assignmentId);
  const topRecentSubmissions = recentSubmissions.slice(0, RECENT_LIMIT);

  return (
    <div className="admin-dashboard" data-testid="admin-dashboard">
      <div className="admin-page-header">
        <h1>{t("admin.dashboard.title")}</h1>
        <span className="hint">
          {user?.role === "admin"
            ? t("admin.dashboard.role.admin")
            : t("admin.dashboard.role.teacher")}
        </span>
      </div>

      <p className="hint">
        {t("admin.dashboard.welcome").replace("{name}", user?.display_name ?? "")}
      </p>

      {loading && <p>{t("admin.dashboard.loading")}</p>}

      {error && (
        <div>
          <p className="error">{t("admin.dashboard.error")}</p>
          <button
            type="button"
            onClick={() => {
              void assignmentsQuery.refetch();
              void problemsQuery.refetch();
              void contestsQuery.refetch();
              void classesQuery.refetch();
            }}
          >
            {t("admin.dashboard.retry")}
          </button>
        </div>
      )}

      {!loading && !error && (
        <>
          {openAssignments.length === 0 &&
            activeContests.length === 0 &&
            topRecentSubmissions.length === 0 && (
            <p>{t("admin.dashboard.empty")}</p>
          )}

          <section
            className="dashboard-section"
            data-testid="active-assignments-section"
          >
            <div className="dashboard-section-header">
              <h2>{t("admin.dashboard.activeAssignments.title")}</h2>
              <Link to="/admin/classes">{t("admin.dashboard.activeAssignments.viewAll")}</Link>
            </div>
            {openAssignments.length === 0 ? (
              <p className="hint">{t("admin.dashboard.activeAssignments.empty")}</p>
            ) : (
              <table data-testid="active-assignments-table">
                <thead>
                  <tr>
                    <th>{t("admin.dashboard.columns.assignment")}</th>
                    <th>{t("admin.dashboard.columns.problem")}</th>
                    <th>{t("admin.dashboard.columns.deadline")}</th>
                  </tr>
                </thead>
                <tbody>
                  {openAssignments.slice(0, RECENT_LIMIT).map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link to={`/admin/assignments/${a.id}`}>
                          #{a.id}
                        </Link>
                      </td>
                      <td>
                        {problemTitles.get(a.problem_id) ?? `#${a.problem_id}`}
                      </td>
                      <td>{formatDeadline(a.deadline)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section
            className="dashboard-section"
            data-testid="upcoming-contests-section"
          >
            <div className="dashboard-section-header">
              <h2>{t("admin.dashboard.upcomingContests.title")}</h2>
              <Link to="/admin/contests" data-testid="view-all-contests-link">
                {t("admin.dashboard.upcomingContests.viewAll")}
              </Link>
            </div>
            {activeContests.length === 0 ? (
              <p className="hint">{t("admin.dashboard.upcomingContests.empty")}</p>
            ) : (
              <table data-testid="upcoming-contests-table">
                <thead>
                  <tr>
                    <th>{t("admin.dashboard.columns.contest")}</th>
                    <th>{t("admin.dashboard.columns.status")}</th>
                  </tr>
                </thead>
                <tbody>
                  {activeContests.slice(0, RECENT_LIMIT).map((c) => (
                    <tr key={c.id}>
                      <td>
                        <Link to={`/admin/contests/${c.id}`}>#{c.id} · {c.title}</Link>
                      </td>
                      <td>
                        <ContestStatusBadge
                          startAt={c.start_at}
                          endAt={c.end_at}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section
            className="dashboard-section"
            data-testid="recent-submissions-section"
          >
            <div className="dashboard-section-header">
              <h2>{t("admin.dashboard.recentSubmissions.title")}</h2>
              <Link to="/submissions" data-testid="view-all-submissions-link">
                {t("admin.dashboard.recentSubmissions.viewAll")}
              </Link>
            </div>
            {topRecentSubmissions.length === 0 ? (
              <p className="hint">{t("admin.dashboard.recentSubmissions.empty")}</p>
            ) : (
              <table data-testid="recent-submissions-table">
                <thead>
                  <tr>
                    <th>{t("admin.dashboard.columns.student")}</th>
                    <th>{t("admin.dashboard.columns.verdict")}</th>
                  </tr>
                </thead>
                <tbody>
                  {topRecentSubmissions.map(({ assignmentId, row }) => (
                    <tr key={`${assignmentId}-${row.user_id}`}>
                      <td>
                        {row.username}{" "}
                        <Link to={`/admin/assignments/${assignmentId}`}>
                          #{assignmentId}
                        </Link>
                      </td>
                      <td>
                        {row.best_verdict ? (
                          <VerdictBadge verdict={row.best_verdict} />
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <p
            className="hint"
            data-testid="flagged-pair-count"
            data-count={flaggedPairCount}
          >
            {flaggedPairCount === 0
              ? t("admin.dashboard.flaggedBadge.zero")
              : `${t("admin.dashboard.flaggedBadge.title")}: ${flaggedPairCount}`}
          </p>
        </>
      )}
    </div>
  );
}