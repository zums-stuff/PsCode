import { useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createRun, getRuns, getRunDetail } from "../lib/api";
import { t } from "../lib/i18n";
import type { RunOut } from "../lib/types";
import BestBadge from "../components/BestBadge";
import RunActions from "../components/RunActions";
import SourceView from "../components/SourceView";
import TestCaseList from "../components/TestCaseList";
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
 * /problem/:id/results — Codeforces-style runs on a single problem.
 * Rows collapsed by default; clicking expands inline (source, verdict,
 * sample cases). Same pattern as /submissions.
 */
export default function ProblemResults() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const problemId = id !== undefined ? Number(id) : null;
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: ["student", "problem-runs", problemId, page],
    queryFn: () => getRuns(page, PAGE_SIZE, problemId ?? undefined),
    enabled: problemId !== null,
  });

  const bestIds = useMemo(
    () => computeBestRunIds(runsQuery.data?.items ?? []),
    [runsQuery.data],
  );

  function toggleExpand(runId: number) {
    setExpandedId((prev) => (prev === runId ? null : runId));
  }

  async function handleRetry(run: RunOut) {
    setRetryError(null);
    try {
      const detail = await getRunDetail(run.id);
      const mode = run.kind === "practice" ? "practice" : run.kind;
      await createRun({
        problemId: run.problem_id,
        source: detail.run.source ?? "",
        mode: mode as "practice" | "assignment" | "contest",
        assignmentId: run.assignment_id,
        contestId: run.contest_id,
      });
      await queryClient.invalidateQueries({
        queryKey: ["student", "problem-runs", problemId, page],
      });
    } catch {
      setRetryError(t("results.retryError"));
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
                <ProblemRunRow
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

interface ProblemRunRowProps {
  run: RunOut;
  expanded: boolean;
  onToggle: () => void;
  isBest: boolean;
  onRetry: () => void;
}

function ProblemRunRow({
  run,
  expanded,
  onToggle,
  isBest,
  onRetry,
}: ProblemRunRowProps) {
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
      {expanded && <ProblemExpandedRow runId={run.id} />}
    </>
  );
}

function ProblemExpandedRow({ runId }: { runId: number }) {
  const detailQuery = useQuery({
    queryKey: ["run", "detail", runId],
    queryFn: () => getRunDetail(runId),
  });

  if (detailQuery.isLoading) {
    return (
      <tr className="run-expanded">
        <td colSpan={8}>
          <p className="hint">{t("results.loading")}</p>
        </td>
      </tr>
    );
  }

  if (detailQuery.isError || detailQuery.data === undefined) {
    return (
      <tr className="run-expanded">
        <td colSpan={8}>
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
      <td colSpan={8}>
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
