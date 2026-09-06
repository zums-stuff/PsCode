import { useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getRuns } from "../lib/api";
import { t } from "../lib/i18n";
import type { RunOut } from "../lib/types";
import BestBadge from "../components/BestBadge";
import RunDetailModal from "../components/RunDetailModal";
import VerdictBadge, { RunStatusBadge } from "../components/VerdictBadge";

const PAGE_SIZE = 20;

/** Verdict priority (plan M7): AC > WA > TLE > RE > CE. */
const VERDICT_PRIORITY: Record<string, number> = {
  AC: 5,
  WA: 4,
  TLE: 3,
  RE: 2,
  CE: 1,
};

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
 * /problem/:id/results — runs the student has on a single problem (plan todo
 * 31). Per-case detail via /api/runs/{id}/detail (hidden-case masking).
 * Same BestBadge + retry semantics as /submissions.
 */
export default function ProblemResults() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const problemId = id !== undefined ? Number(id) : null;
  const [page, setPage] = useState(1);
  const [openRunId, setOpenRunId] = useState<number | null>(null);

  const runsQuery = useQuery({
    queryKey: ["student", "problem-runs", problemId, page],
    queryFn: () => getRuns(page, PAGE_SIZE, problemId ?? undefined),
    enabled: problemId !== null,
  });

  const bestIds = useMemo(
    () => computeBestRunIds(runsQuery.data?.items ?? []),
    [runsQuery.data],
  );

  async function handleRetry(run: RunOut) {
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
      await queryClient.invalidateQueries({
        queryKey: ["student", "problem-runs", problemId, page],
      });
    } catch {
      // surfaced via the runs query on next refetch
    }
  }

  return (
    <div>
      <h1>
        {t("results.problemResults.title")}
        {problemId !== null && ` #${problemId}`}
      </h1>
      <p>
        <Link to={`/problem/${problemId}`}>{t("results.problemResults.back")}</Link>
      </p>

      {runsQuery.isLoading && <p>{t("results.loading")}</p>}
      {runsQuery.isError && (
        <p className="error">{t("results.loadError")}</p>
      )}

      {runsQuery.data !== undefined && runsQuery.data.items.length === 0 && (
        <p className="hint">{t("results.empty")}</p>
      )}

      {runsQuery.data !== undefined && runsQuery.data.items.length > 0 && (
        <>
          <table className="data-table">
            <thead>
              <tr>
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
        <RunDetailModal
          runId={openRunId}
          problemTitle={`#${problemId}`}
          onClose={() => setOpenRunId(null)}
        />
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
