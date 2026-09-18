import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, getRuns, getRunDetail } from "../lib/api";
import { t } from "../lib/i18n";
import type {
  Contest,
  ProblemOut,
  RunDetailOut,
  RunDetailResponse,
  RunOut,
  TestCaseOut,
} from "../lib/types";
import CodeMirrorEditor from "../components/CodeMirrorEditor";
import PracticeOutputPanel from "../components/PracticeOutputPanel";
import SolveStatementPane from "../components/SolveStatementPane";
import SolveResultsPane from "../components/SolveResultsPane";
import SolveToolbar from "../components/SolveToolbar";
import VerdictBadge from "../components/VerdictBadge";
import { SkeletonRow } from "../components/Skeleton";
import { useSubmitShortcut } from "../lib/useSubmitShortcut";
import "./Solve.css";

const TERMINAL_STATUSES = new Set(["done", "failed"]);

function MyRunExpandedRow({ runId }: { runId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["run", runId, "detail"],
    queryFn: () => getRunDetail(runId),
  });

  return (
    <tr className="my-runs-expanded-row">
      <td colSpan={3}>
        {isLoading && <SkeletonRow lines={2} />}
        {isError && <p className="error">{t("results.loadError")}</p>}
        {data && (
          <div className="my-runs-expanded-content">
            <p className="my-runs-expanded-title">{t("solve.expandedRun")} #{runId}</p>
            <RunDetailCasesTable detail={data} />
          </div>
        )}
      </td>
    </tr>
  );
}

function RunDetailCasesTable({ detail }: { detail: RunDetailResponse }) {
  if (detail.test_cases.length === 0) {
    return <p className="hint">{t("results.modal.empty")}</p>;
  }
  return (
    <table className="my-runs-cases-table">
      <thead>
        <tr>
          <th>{t("solve.results.case")}</th>
          <th>{t("solve.results.verdict")}</th>
          <th>{t("solve.results.steps")}</th>
          <th>{t("solve.results.wall")}</th>
        </tr>
      </thead>
      <tbody>
        {detail.test_cases.map((tc) => (
          <tr key={tc.case_index}>
            <td>{tc.case_index + 1}</td>
            <td>
              <VerdictBadge verdict={tc.verdict} />
            </td>
            <td>{tc.steps ?? "—"}</td>
            <td>{tc.wall_ms ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MyRunRow({
  run,
  expanded,
  onToggle,
}: {
  run: RunOut;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="my-runs-row"
        data-testid={`my-run-${run.id}`}
      >
        <td style={{ textAlign: "left" }}>
          {new Date(run.created_at).toLocaleString()}
        </td>
        <td>
          <VerdictBadge verdict={run.summary_verdict ?? "—"} />
        </td>
        <td>{run.steps ?? "—"}</td>
      </tr>
      {expanded && <MyRunExpandedRow runId={run.id} />}
    </>
  );
}

/**
 * Student solve page (plan todo 29): Codeforces-like layout with full-width
 * statement on top, then a 2-col grid (editor | sidebar with previous
 * submissions). Loads previous runs on mount via GET /api/runs?problem_id=X.
 */
export default function Solve() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const assignmentId = searchParams.get("assignment");
  const contestId = searchParams.get("contest");
  const problemId = id !== undefined ? Number(id) : undefined;
  const [source, setSource] = useState("");
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetailOut | null>(null);
  const [practiceRunId, setPracticeRunId] = useState<number | null>(null);
  const [practiceRun, setPracticeRun] = useState<RunDetailOut | null>(null);
  const [practiceStdin, setPracticeStdin] = useState("");
  const [testCases, setTestCases] = useState<TestCaseOut[]>([]);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);

  const problemQuery = useQuery({
    queryKey: ["problem", id],
    queryFn: () => api.get<ProblemOut>(`/api/problems/${id}`),
    enabled: id !== undefined,
  });

  const myRunsQuery = useQuery({
    queryKey: ["my-runs", problemId],
    queryFn: () => getRuns(1, 10, problemId),
    enabled: problemId !== undefined,
  });

  const contestQuery = useQuery({
    queryKey: ["contest", contestId],
    queryFn: () => api.get<Contest>(`/api/contests/${contestId}`),
    enabled: contestId !== null,
  });

  useEffect(() => {
    if (problemQuery.data === undefined) return;
    let cancelled = false;
    api
      .get<TestCaseOut[]>(`/api/problems/${problemQuery.data.id}/cases`)
      .then((cases) => {
        if (!cancelled) setTestCases(cases);
      })
      .catch(() => {
        // sample input is best-effort
      });
    return () => {
      cancelled = true;
    };
  }, [problemQuery.data]);

  useEffect(() => {
    if (runId === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function poll() {
      try {
        const r = await api.get<RunDetailOut>(`/api/runs/${runId}`);
        if (cancelled) return;
        setRun(r);
        if (TERMINAL_STATUSES.has(r.status)) return;
      } catch {
        // transient
      }
      timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (practiceRunId === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function poll() {
      try {
        const r = await api.get<RunDetailOut>(`/api/runs/${practiceRunId}`);
        if (cancelled) return;
        setPracticeRun(r);
        if (TERMINAL_STATUSES.has(r.status)) return;
      } catch {
        // transient
      }
      timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [practiceRunId]);

  const handleSubmit = useCallback(() => {
    const btn = document.querySelector<HTMLButtonElement>(
      ".solve-toolbar .primary:not(:disabled)",
    );
    btn?.click();
  }, []);
  useSubmitShortcut(handleSubmit);

  if (problemQuery.isLoading) {
    return (
      <div className="solve-page">
        <h1 className="solve-page-title">{t("solve.title")}</h1>
        <SkeletonRow lines={4} />
      </div>
    );
  }
  if (problemQuery.isError || problemQuery.data === undefined) {
    return <p className="error">{t("solve.error")}</p>;
  }
  const problem = problemQuery.data;

  return (
    <div className="solve-page">
      <h1 className="solve-page-title">
        {t("solve.title")} — {problem.title}
      </h1>

      <section className="solve-statement-section">
        <SolveStatementPane problem={problem} />
      </section>

      <div className="solve-grid">
        <section className="solve-editor-section">
          <h2>{t("solve.editor")}</h2>
          <SolveToolbar
            problemId={problem.id}
            source={source}
            assignmentId={assignmentId}
            contestId={contestId}
            onRunCreated={setRunId}
            onPracticeRunCreated={(runId, stdin) => {
              setPracticeRunId(runId);
              setPracticeStdin(stdin);
              setPracticeRun(null);
            }}
            onReset={() => setSource("")}
          />
          <div className="solve-editor">
            <CodeMirrorEditor value={source} onChange={setSource} />
          </div>
          <PracticeOutputPanel
            run={practiceRun}
            testCases={testCases}
            stdin={practiceStdin}
            stepBudget={problem.step_budget}
          />
          <SolveResultsPane run={run} testCases={testCases} />
        </section>

        <aside className="solve-sidebar">
          {contestId !== null && contestQuery.data && (
            <div className="solve-contest-materials">
              <h3>{t("solve.contestMaterials")}</h3>
              <a href={`/contest/${contestId}`}>{t("solve.openContest")}</a>
            </div>
          )}
          <div className="solve-my-runs">
            <h3>{t("solve.mySubmissions")}</h3>
            {myRunsQuery.isLoading && <SkeletonRow lines={3} />}
            {myRunsQuery.isError && (
              <p className="error">{t("solve.myRunsError")}</p>
            )}
            {myRunsQuery.data && myRunsQuery.data.items.length === 0 && (
              <p className="hint">{t("solve.noSubmissions")}</p>
            )}
            {myRunsQuery.data && myRunsQuery.data.items.length > 0 && (
              <table className="my-runs-table">
                <thead>
                  <tr>
                    <th>{t("solve.col.when")}</th>
                    <th>{t("solve.col.verdict")}</th>
                    <th>{t("solve.col.time")}</th>
                  </tr>
                </thead>
                <tbody>
                  {myRunsQuery.data.items.map((r) => (
                    <MyRunRow
                      key={r.id}
                      run={r}
                      expanded={expandedRunId === r.id}
                      onToggle={() =>
                        setExpandedRunId(
                          r.id === expandedRunId ? null : r.id,
                        )
                      }
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </aside>
      </div>

      <div className="solve-sticky-bar">
        <button
          type="button"
          className="primary"
          onClick={handleSubmit}
          aria-label={`${t("solve.submit")} (${t("solve.submitShortcut")})`}
        >
          <span aria-hidden="true">{t("solve.submit")}</span>
          <span className="solve-shortcut-hint" aria-hidden="true">
            {t("solve.submitShortcut")}
          </span>
        </button>
      </div>
    </div>
  );
}
