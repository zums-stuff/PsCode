import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { Filters, Page, ProblemListItem } from "../../lib/types";
import ProblemsFilter from "../../components/ProblemsFilter";

export default function Problems() {
  const [filters, setFilters] = useState<Filters>({
    complexity: [],
    solved: "all",
    query: "",
  });

  const problemsQuery = useQuery({
    queryKey: ["student", "problems"],
    queryFn: () =>
      api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
  });

  const displayed = useMemo(() => {
    const items = problemsQuery.data?.items ?? [];
    return items.filter((p) => {
      if (filters.complexity.length && !filters.complexity.includes(p.expected_complexity)) {
        return false;
      }
      if (filters.solved === "solved" && !p.is_solved) return false;
      if (filters.solved === "unsolved" && p.is_solved) return false;
      if (filters.query) {
        const q = filters.query.trim().toLowerCase();
        if (q && !p.title.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [problemsQuery.data, filters]);

  if (problemsQuery.isLoading) {
    return <p>{t("student.problems.loading")}</p>;
  }
  if (problemsQuery.isError) {
    return <p className="error">{t("student.problems.error")}</p>;
  }

  return (
    <div>
      <h1>
        {t("student.problems.title")}{" "}
        <span className="problems-count">({displayed.length} problema(s))</span>
      </h1>
      <ProblemsFilter value={filters} onChange={setFilters} />
      {displayed.length === 0 ? (
        <p>{t("student.problems.empty")}</p>
      ) : (
        <table className="datatable">
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
            {displayed.map((problem) => (
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
      )}
    </div>
  );
}
