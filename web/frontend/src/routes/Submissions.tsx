import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { createRun, getRuns, getRunDetail } from "../lib/api";
import { t } from "../lib/i18n";
import type { RunOut } from "../lib/types";
import BestBadge from "../components/BestBadge";
import RunActions from "../components/RunActions";
import SourceView from "../components/SourceView";
import TestCaseList from "../components/TestCaseList";
import VerdictBadge, { RunStatusBadge } from "../components/VerdictBadge";
import { useRunSocket } from "../lib/ws";

const PAGE_SIZE = 20;

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
 * /submissions — paginated Codeforces-style table of the student's runs.
 * Rows are collapsed by default; clicking expands inline to show source,
 * verdict, and sample test cases. Hidden cases are omitted from collapsed
 * view and shown with "(oculto)" in expanded view.
 */
export default function Submissions() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  const { events } = useRunSocket();

  const runsQuery = useQuery({
    queryKey: ["student", "runs", page],
    queryFn: () => getRuns(page, PAGE_SIZE),
  });

  useEffect(() => {
    if (events.length === 0) return;
    void queryClient.invalidateQueries({ queryKey: ["student", "runs"] });
  }, [events.length, queryClient]);

  const bestIds = useMemo(
    () => computeBestRunIds(runsQuery.data?.items ?? []),
    [runsQuery.data],
  );

  function toggleExpand(id: number) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  async function handleRetry(run: RunOut) {
    setRetryError(null);
    try {
      // Re-submit the run's REAL source (the list payload omits it), as a
      // practice sandbox run when the original was practice, otherwise in the
      // original mode (Bug A — previous code posted an empty source).
      const detail = await getRunDetail(run.id);
      const mode = run.kind === "practice" ? "practice" : run.kind;
      await createRun({
        problemId: run.problem_id,
        source: detail.run.source ?? "",
        mode: mode as "practice" | "assignment" | "contest",
        assignmentId: run.assignment_id,
        contestId: run.contest_id,
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
                <th />
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
                <RunRow
                  key={run.id}
                  run={run}
                  expanded={expandedId === run.id}
                  onToggle={() => toggleExpand(run.id)}
                  isBest={bestIds.has(run.id)}
                  onRetry={() => void handleRetry(run)}
                />
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
    </div>
  );
}

interface RunRowProps {
  run: RunOut;
  expanded: boolean;
  onToggle: () => void;
  isBest: boolean;
  onRetry: () => void;
}

function RunRow({ run, expanded, onToggle, isBest, onRetry }: RunRowProps) {
  return (
    <>
      <tr
        className="run-row"
        onClick={onToggle}
        style={{ cursor: "pointer" }}
        aria-expanded={expanded}
      >
        <td>{expanded ? "▼" : "▶"}</td>
        <td>
          <Link to={`/problem/${run.problem_id}`} onClick={(e) => e.stopPropagation()}>
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
          {isBest && (
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
          <RunActions run={run} onViewDetail={onToggle} onResubmit={onRetry} />
        </td>
      </tr>
      {expanded && <ExpandedRow runId={run.id} />}
    </>
  );
}

function ExpandedRow({ runId }: { runId: number }) {
  const detailQuery = useQuery({
    queryKey: ["run", "detail", runId],
    queryFn: () => getRunDetail(runId),
  });

  if (detailQuery.isLoading) {
    return (
      <tr className="run-expanded">
        <td colSpan={9}>
          <p className="hint">{t("results.loading")}</p>
        </td>
      </tr>
    );
  }

  if (detailQuery.isError || detailQuery.data === undefined) {
    return (
      <tr className="run-expanded">
        <td colSpan={9}>
          <p className="error">{t("results.loadError")}</p>
        </td>
      </tr>
    );
  }

  const { run, test_cases } = detailQuery.data;
  const sampleFirst = [...test_cases].sort((a, b) =>
    Number(b.is_sample) - Number(a.is_sample),
  );

  return (
    <tr className="run-expanded">
      <td colSpan={9}>
        <div className="run-expanded-content">
          {run.summary_verdict !== null && (
            <p>
              <strong>{t("submissions.verdict")}:</strong>{" "}
              <VerdictBadge verdict={run.summary_verdict} />
            </p>
          )}

          <section>
            <h4>{t("submissions.code")}</h4>
            <SourceView source={run.source ?? ""} />
          </section>

          {sampleFirst.length > 0 && (
            <section>
              <h4>{t("submissions.sampleCases")}</h4>
              <TestCaseList cases={sampleFirst} limit={2} />
            </section>
          )}
        </div>
      </td>
    </tr>
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
