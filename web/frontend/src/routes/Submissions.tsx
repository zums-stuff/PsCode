import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getRuns } from "../lib/api";
import { t } from "../lib/i18n";
import type { RunOut } from "../lib/types";
import BestBadge from "../components/BestBadge";
import RunDetailModal from "../components/RunDetailModal";
import VerdictBadge, { RunStatusBadge } from "../components/VerdictBadge";
import { useRunSocket } from "../lib/ws";

const PAGE_SIZE = 20;

/** Verdict priority (plan M7): AC > WA > TLE > RE > CE. */
const VERDICT_PRIORITY: Record<string, number> = {
  AC: 5,
  WA: 4,
  TLE: 3,
  RE: 2,
  CE: 1,
};

/** Compute the assignment-best run ids in the page: for each
 *  (problem_id, assignment_id) group, the run with highest verdict
 *  priority and fewest steps among ties. Practice runs are not best. */
function computeBestRunIds(runs: RunOut[]): Set<number> {
  const groups = new Map<string, RunOut[]>();
  for (const run of runs) {
    if (run.assignment_id === null) continue;
    const key = `${run.problem_id}-${run.assignment_id}`;
    const list = groups.get(key) ?? [];
    list.push(run);
    groups.set(key, list);
  }
  const bestIds = new Set<number>();
  for (const group of groups.values()) {
    let best: RunOut | null = null;
    for (const run of group) {
      if (best === null) {
        best = run;
        continue;
      }
      const bp = VERDICT_PRIORITY[best.summary_verdict ?? ""] ?? 0;
      const rp = VERDICT_PRIORITY[run.summary_verdict ?? ""] ?? 0;
      if (rp > bp) {
        best = run;
      } else if (rp === bp && (run.steps ?? Infinity) < (best.steps ?? Infinity)) {
        best = run;
      }
    }
    if (best !== null) bestIds.add(best.id);
  }
  return bestIds;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
}

/**
 * /submissions — paginated table of the student's runs (plan todo 31).
 * Live-updates via WS: any run event refetches the current page. Rows open
 * the RunDetailModal; failed-transport (status=failed) rows get a Retry
 * button that re-POSTs /api/runs.
 */
export default function Submissions() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [openRunId, setOpenRunId] = useState<number | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  const { events } = useRunSocket();

  const runsQuery = useQuery({
    queryKey: ["student", "runs", page],
    queryFn: () => getRuns(page, PAGE_SIZE),
  });

  // Refetch the runs list whenever a WS run event arrives (plan todo 31).
  useEffect(() => {
    if (events.length === 0) return;
    void queryClient.invalidateQueries({ queryKey: ["student", "runs"] });
  }, [events.length, queryClient]);

  const bestIds = useMemo(
    () => computeBestRunIds(runsQuery.data?.items ?? []),
    [runsQuery.data],
  );

  async function handleRetry(run: RunOut) {
    setRetryError(null);
    try {
      await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          problem_id: run.problem_id,
          source: "",
          mode: run.kind,
          assignment_id: run.assignment_id,
          contest_id: run.contest_id,
        }),
      });
      await queryClient.invalidateQueries({ queryKey: ["student", "runs"] });
    } catch {
      setRetryError(t("results.retryError"));
    }
  }

  return (
    <div>
      <h1>{t("student.submissions.title")}</h1>

      {runsQuery.isLoading && <p>{t("results.loading")}</p>}
      {runsQuery.isError && (
        <div>
          <p className="error">{t("results.loadError")}</p>
          <button type="button" onClick={() => runsQuery.refetch()}>
            {t("results.retry")}
          </button>
        </div>
      )}
      {retryError && <p className="error">{retryError}</p>}

      {runsQuery.data !== undefined && runsQuery.data.items.length === 0 && (
        <p className="hint">{t("results.empty")}</p>
      )}

      {runsQuery.data !== undefined && runsQuery.data.items.length > 0 && (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("results.columns.problem")}</th>
                <th>{t("results.columns.status")}</th>
                <th>{t("results.columns.verdict")}</th>
                <th>{t("results.columns.steps")}</th>
                <th>{t("results.columns.wall")}</th>
                <th>{t("results.columns.submitted")}</th>
                <th>{t("results.columns.kind")}</th>
                <th>{t("results.columns.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {runsQuery.data.items.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link to={`/problem/${run.problem_id}`}>
                      #{run.problem_id}
                    </Link>
                  </td>
                  <td>
                    <RunStatusBadge status={run.status} />
                  </td>
                  <td>
                    {run.summary_verdict !== null ? (
                      <VerdictBadge verdict={run.summary_verdict} />
                    ) : (
                      "—"
                    )}
                    {bestIds.has(run.id) && (
                      <>
                        {" "}
                        <BestBadge />
                      </>
                    )}
                  </td>
                  <td>{run.steps ?? "—"}</td>
                  <td>{run.wall_ms ?? "—"}</td>
                  <td>{formatDate(run.created_at)}</td>
                  <td>{t(`results.kind.${run.kind}`)}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => setOpenRunId(run.id)}
                    >
                      {t("results.view")}
                    </button>
                    {run.status === "failed" && (
                      <button
                        type="button"
                        className="primary"
                        onClick={() => void handleRetry(run)}
                      >
                        {t("results.retry")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <Pagination
            page={page}
            size={PAGE_SIZE}
            total={runsQuery.data.total}
            onPageChange={setPage}
          />
        </>
      )}

      {openRunId !== null && (
        <RunDetailModal runId={openRunId} onClose={() => setOpenRunId(null)} />
      )}
    </div>
  );
}

interface PaginationProps {
  page: number;
  size: number;
  total: number;
  onPageChange: (page: number) => void;
}

function Pagination({ page, size, total, onPageChange }: PaginationProps) {
  const lastPage = Math.max(1, Math.ceil(total / size));
  return (
    <div className="pagination">
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
      >
        {t("results.pagination.prev")}
      </button>
      <span>
        {t("results.pagination.label")} {page} / {lastPage}
      </span>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= lastPage}
      >
        {t("results.pagination.next")}
      </button>
    </div>
  );
}
