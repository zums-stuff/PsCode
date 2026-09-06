import { Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, getAssignmentSubmissions } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import type { AssignmentListItem, Page } from "../../lib/types";
import AssignmentSubmissionsTable from "../../components/AssignmentSubmissionsTable";

/** /admin/assignments/:id — per-student best submissions + rejudge. */
export default function AdminAssignmentDetail() {
  const { id } = useParams();
  const { user } = useAuth();

  if (user?.role === "student") {
    return <Navigate to="/403" replace />;
  }

  const assignmentQuery = useQuery({
    queryKey: ["admin", "assignments"],
    queryFn: () =>
      api.get<Page<AssignmentListItem>>("/api/assignments?page=1&size=100"),
  });

  const assignment = assignmentQuery.data?.items.find((a) => a.id === Number(id));

  const submissionsQuery = useQuery({
    queryKey: ["admin", "assignment", id, "submissions"],
    queryFn: () => getAssignmentSubmissions(Number(id)),
    enabled: assignment !== undefined,
  });

  if (assignmentQuery.isLoading) {
    return <p>{t("admin.assignments.loading")}</p>;
  }

  if (assignmentQuery.isError) {
    return <p className="error">{t("admin.assignments.loadError")}</p>;
  }

  if (assignment === undefined) {
    return <p className="error">{t("admin.assignments.notFound")}</p>;
  }

  return (
    <div>
      <h1>
        {t("admin.assignments.submissions")} — #{assignment.id}
      </h1>
      {submissionsQuery.isLoading && <p>{t("admin.assignments.loading")}</p>}
      {submissionsQuery.isError && (
        <p className="error">{t("admin.assignments.loadError")}</p>
      )}
      {submissionsQuery.data && (
        <AssignmentSubmissionsTable
          assignmentId={assignment.id}
          problemId={assignment.problem_id}
          rows={submissionsQuery.data}
          onRejudged={() => submissionsQuery.refetch()}
        />
      )}
    </div>
  );
}