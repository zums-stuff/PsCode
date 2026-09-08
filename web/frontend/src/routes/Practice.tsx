import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getProblemCases } from "../lib/api";
import { t } from "../lib/i18n";
import type {
  Page,
  ProblemListItem,
  ProblemOut,
  RunDetailOut,
  RunOut,
} from "../lib/types";
import CodeMirrorEditor from "../components/CodeMirrorEditor";
import Markdown from "../components/Markdown";
import PracticeOutputPanel from "../components/PracticeOutputPanel";
import RunModal from "../components/RunModal";
import VerdictBadge, { RunStatusBadge } from "../components/VerdictBadge";
import { useRunSocket } from "../lib/ws";

const TERMINAL_STATUSES = new Set(["done", "failed"]);
const HISTORY_SIZE = 5;
const POLL_MS = 2000;

/**
 * Derive a PseInt procedure name from a problem title for the default source
 * template (plan todo 30): strip diacritics, collapse non-word runs to
 * underscores, never start with a digit.
 */
function templateSource(title: string): string {
  const ascii = title.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const name = ascii.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const safe = /^\d/.test(name) ? `_${name}` : name;
  return `Proceso ${safe || "Main"}\n\nFinProceso`;
}

/**
 * /practice — practice sandbox (plan todo 30 / C4). Works standalone (just
 * editor + stdin + output) or with a problem selected (statement, sample
 * input pre-fill, per-case output). The "Pick a problem" section is
 * collapsible; the Run button is disabled when no problem is selected.
 */
export default function Practice() {
  const queryClient = useQueryClient();
  const [problemId, setProblemId] = useState<number | null>(null);
  const [source, setSource] = useState("Proceso P\n\nFinProceso");
  const [stdin, setStdin] = useState("");
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetailOut | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const { events } = useRunSocket();

  const problemsQuery = useQuery({
    queryKey: ["practice", "problems"],
    queryFn: () =>
      api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
  });

  const problemQuery = useQuery({
    queryKey: ["problem", problemId],
    queryFn: () => api.get<ProblemOut>(`/api/problems/${problemId}`),
    enabled: problemId !== null,
  });

  const casesQuery = useQuery({
    queryKey: ["problem", problemId, "cases"],
    queryFn: () => getProblemCases(problemId as number),
    enabled: problemId !== null,
  });

  const historyQuery = useQuery({
    queryKey: ["practice", "history", problemId],
    queryFn: () =>
      api.get<Page<RunOut>>(
        `/api/runs?page=1&size=${HISTORY_SIZE}&problem_id=${problemId}`,
      ),
    enabled: problemId !== null,
  });

  const practiceRuns = (historyQuery.data?.items ?? []).filter(
    (r) => r.kind === "practice",
  );

  // Poll the active run until a terminal status (fallback; WS accelerates).
  useEffect(() => {
    if (runId === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function poll() {
      try {
        const detail = await api.get<RunDetailOut>(`/api/runs/${runId}`);
        if (cancelled) return;
        setRun(detail);
        if (TERMINAL_STATUSES.has(detail.status)) return;
      } catch {
        // transient — keep polling
      }
      timer = setTimeout(poll, POLL_MS);
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [runId]);

  // WS events: refetch the history strip and, when the event matches the
  // active run, refresh its detail immediately.
  useEffect(() => {
    if (events.length === 0) return;
    void queryClient.invalidateQueries({ queryKey: ["practice", "history"] });
    const latest = events[events.length - 1];
    if (runId !== null && latest.submission_id === runId) {
      void api
        .get<RunDetailOut>(`/api/runs/${runId}`)
        .then((detail) => setRun(detail))
        .catch(() => {
          // transient — the poll loop will pick it up
        });
    }
  }, [events, queryClient, runId]);

  function handleProblemChange(value: string) {
    const id = value === "" ? null : Number(value);
    setProblemId(id);
    setRunId(null);
    setRun(null);
    setStdin("");
    setModalOpen(false);
    if (id !== null) {
      const item = problemsQuery.data?.items.find((p) => p.id === id);
      setSource(item !== undefined ? templateSource(item.title) : "Proceso P\n\nFinProceso");
    } else {
      setSource("Proceso P\n\nFinProceso");
    }
  }

  function handleRunCreated(newRunId: number, newStdin: string) {
    setStdin(newStdin);
    setRunId(newRunId);
    setRun(null);
    if (problemId !== null) {
      void queryClient.invalidateQueries({
        queryKey: ["practice", "history", problemId],
      });
    }
  }

  function handleHistorySelect(id: number) {
    setRunId(id);
    setRun(null);
  }

  if (problemsQuery.isLoading) {
    return (
      <div>
        <h1>{t("student.practice.title")}</h1>
        <p>{t("student.practice.loading")}</p>
      </div>
    );
  }

  return (
    <div className="practice-page">
      <h1>{t("student.practice.title")}</h1>
      <p className="hint">{t("student.practice.subtitle")}</p>

      {problemsQuery.isError ? (
        <p className="error">{t("student.practice.error")}</p>
      ) : (
        <details className="practice-problem-picker" open={problemId !== null}>
          <summary>{t("student.practice.selectProblem")}</summary>
          <select
            className="practice-select"
            value={problemId ?? ""}
            onChange={(e) => handleProblemChange(e.target.value)}
            data-testid="practice-problem-select"
          >
            <option value="">{t("student.practice.selectProblem")}</option>
            {problemsQuery.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </details>
      )}

      {problemQuery.isError && (
        <p className="error">{t("student.practice.error")}</p>
      )}

      {problemId === null && (
        <p className="hint practice-standalone-hint">{t("student.practice.standalone")}</p>
      )}

      <div className="practice-grid">
        {problemQuery.data !== undefined && (
          <section className="practice-statement">
            <h2>{problemQuery.data.title}</h2>
            <Markdown source={problemQuery.data.statement} />
          </section>
        )}

        <section className="practice-editor">
          <div className="practice-toolbar">
            <button
              type="button"
              className="primary"
              onClick={() => setModalOpen(true)}
            >
              {t("student.practice.run")}
            </button>
            <button
              type="button"
              onClick={() =>
                setSource(
                  problemQuery.data !== undefined
                    ? templateSource(problemQuery.data.title)
                    : "Proceso P\n\nFinProceso",
                )
              }
            >
              {t("solve.reset")}
            </button>
          </div>
          {problemId === null && (
            <p className="hint">{t("student.practice.noProblemSelected")}</p>
          )}
          <CodeMirrorEditor value={source} onChange={setSource} />
          {run !== null ? (
            <PracticeOutputPanel
              run={run}
              testCases={casesQuery.data ?? []}
              stdin={stdin}
              stepBudget={problemQuery.data?.step_budget ?? null}
            />
          ) : (
            <section className="solve-results">
              <h2>{t("solve.practice.title")}</h2>
              <p className="hint">{t("student.practice.outputPlaceholder")}</p>
            </section>
          )}
        </section>

        <section className="practice-history">
          <h2>{t("student.practice.history")}</h2>
          {problemId === null ? (
            <p className="hint">{t("student.practice.noProblemSelected")}</p>
          ) : (
            <>
              {historyQuery.isLoading && (
                <p className="hint">{t("solve.loading")}</p>
              )}
              {historyQuery.isError && (
                <p className="error">{t("student.practice.error")}</p>
              )}
              {historyQuery.data !== undefined && practiceRuns.length === 0 && (
                <p className="hint">{t("student.practice.emptyHistory")}</p>
              )}
              {practiceRuns.length > 0 && (
                <ul className="practice-history-list">
                  {practiceRuns.map((r) => (
                    <li key={r.id}>
                      <button
                        type="button"
                        className={
                          r.id === runId ? "practice-history-active" : undefined
                        }
                        onClick={() => handleHistorySelect(r.id)}
                      >
                        <span className="practice-run-id">#{r.id}</span>
                        {r.summary_verdict !== null ? (
                          <VerdictBadge verdict={r.summary_verdict} />
                        ) : r.status === "done" || r.status === "failed" ? (
                          <span className="hint">{t("student.practice.noCase")}</span>
                        ) : (
                          <RunStatusBadge status={r.status} />
                        )}
                        <span className="practice-run-steps">
                          {r.steps ?? "—"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      </div>

      {modalOpen && (
        <RunModal
          problemId={problemId}
          source={source}
          onClose={() => setModalOpen(false)}
          onRunCreated={handleRunCreated}
        />
      )}
    </div>
  );
}