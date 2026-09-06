import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { Page, ProblemListItem } from "../../lib/types";

/**
 * Student problems list (plan todo 27 landing page). The full solve page
 * (statement + editor) is todo 29; this is the shell-level list.
 */
export default function Problems() {
  const problemsQuery = useQuery({
    queryKey: ["student", "problems"],
    queryFn: () =>
      api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
  });

  if (problemsQuery.isLoading) {
    return <p>{t("student.problems.loading")}</p>;
  }
  if (problemsQuery.isError) {
    return <p className="error">{t("student.problems.error")}</p>;
  }

  const problems = problemsQuery.data?.items ?? [];
  if (problems.length === 0) {
    return <p>{t("student.problems.empty")}</p>;
  }

  return (
    <div>
      <h1>{t("student.problems.title")}</h1>
      <table className="data-table">
        <thead>
          <tr>
            <th>{t("student.problems.columns.id")}</th>
            <th>{t("student.problems.columns.title")}</th>
            <th>{t("student.problems.columns.complexity")}</th>
            <th>{t("student.problems.columns.solved")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {problems.map((problem) => (
            <tr key={problem.id}>
              <td>{problem.id}</td>
              <td>{problem.title}</td>
              <td>{problem.expected_complexity}</td>
              <td>
                {problem.is_solved
                  ? t("student.problems.solved.yes")
                  : t("student.problems.solved.no")}
              </td>
              <td>
                <Link to={`/problem/${problem.id}`}>
                  {t("student.problems.open")}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}