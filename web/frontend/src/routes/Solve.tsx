import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type { ProblemOut, RunDetailOut, TestCaseOut } from "../lib/types";
import CodeMirrorEditor from "../components/CodeMirrorEditor";
import PracticeOutputPanel from "../components/PracticeOutputPanel";
import SolveStatementPane from "../components/SolveStatementPane";
import SolveResultsPane from "../components/SolveResultsPane";
import SolveToolbar from "../components/SolveToolbar";
import "./Solve.css";

const TERMINAL_STATUSES = new Set(["done", "failed"]);

/**
 * Student solve page (plan todo 29): statement pane + CodeMirror editor with
 * debounced inline syntax errors + results pane. Desktop 3-pane grid, mobile
 * stacked. Submit enqueues a run (POST /api/runs); the results pane polls
 * GET /api/runs/{id} every 1s until a terminal status (WS surface is a later
 * todo). "Ejecutar muestra" (todo 30) enqueues a practice run with custom
 * stdin; its output renders in PracticeOutputPanel below the editor.
 */
export default function Solve() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const assignmentId = searchParams.get("assignment");
  const contestId = searchParams.get("contest");
  const [source, setSource] = useState("");
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetailOut | null>(null);
  const [practiceRunId, setPracticeRunId] = useState<number | null>(null);
  const [practiceRun, setPracticeRun] = useState<RunDetailOut | null>(null);
  const [practiceStdin, setPracticeStdin] = useState("");
  const [testCases, setTestCases] = useState<TestCaseOut[]>([]);

  const problemQuery = useQuery({
    queryKey: ["problem", id],
    queryFn: () => api.get<ProblemOut>(`/api/problems/${id}`),
    enabled: id !== undefined,
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
        // sample input is best-effort; the modal shows its own error
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
        // transient — keep polling
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
        // transient — keep polling
      }
      timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [practiceRunId]);

  if (problemQuery.isLoading) {
    return <p>{t("solve.loading")}</p>;
  }
  if (problemQuery.isError || problemQuery.data === undefined) {
    return <p className="error">{t("solve.error")}</p>;
  }
  const problem = problemQuery.data;

  return (
    <div>
      <h1>{t("solve.title")}</h1>
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
      <div className="solve-grid">
        <SolveStatementPane problem={problem} />
        <section className="solve-editor">
          <h2>{t("solve.statement")}</h2>
          <CodeMirrorEditor value={source} onChange={setSource} />
          <PracticeOutputPanel
            run={practiceRun}
            testCases={testCases}
            stdin={practiceStdin}
            stepBudget={problem.step_budget}
          />
        </section>
        <SolveResultsPane run={run} />
      </div>
    </div>
  );
}