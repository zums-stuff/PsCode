import { useCallback, useEffect, useState } from "react";
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
import PracticeOutputPanel from "../components/PracticeOutputPanel";
import RunModal from "../components/RunModal";
import VerdictBadge from "../components/VerdictBadge";
import SolveStatementPane from "../components/SolveStatementPane";
import { SkeletonRow } from "../components/Skeleton";
import { useRunSocket } from "../lib/ws";
import { useSubmitShortcut } from "../lib/useSubmitShortcut";

const TERMINAL_STATUSES = new Set(["done", "failed"]);
const HISTORY_SIZE = 10;
const POLL_MS = 2000;

function templateSource(title: string): string {
  const ascii = title.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const name = ascii.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const safe = /^\d/.test(name) ? `_${name}` : name;
  return `Proceso ${safe || "Main"}\n\nFinProceso`;
}

export default function Practice() {
  const queryClient = useQueryClient();
  const [problemId, setProblemId] = useState<number | null>(null);
  const [source, setSource] = useState("Proceso P\n\nFinProceso");
  const [stdin, setStdin] = useState("");
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetailOut | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null);

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
        // transient
      }
      timer = setTimeout(poll, POLL_MS);
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (events.length === 0) return;
    void queryClient.invalidateQueries({ queryKey: ["practice", "history"] });
    const latest = events[events.length - 1];
    if (runId !== null && latest.submission_id === runId) {
      void api
        .get<RunDetailOut>(`/api/runs/${runId}`)
        .then((detail) => setRun(detail))
        .catch(() => {
          // transient
        });
    }
  }, [events, queryClient, runId]);

  const handleOpenRunModal = useCallback(() => setModalOpen(true), []);
  useSubmitShortcut(handleOpenRunModal);

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

  function resetCode() {
    if (problemId !== null) {
      const item = problemsQuery.data?.items.find((p) => p.id === problemId);
      setSource(item !== undefined ? templateSource(item.title) : "Proceso P\n\nFinProceso");
    } else {
      setSource("Proceso P\n\nFinProceso");
    }
  }

  if (problemsQuery.isLoading) {
    return (
      <div className="practice-page">
        <h1>{t("student.practice.title")}</h1>
        <SkeletonRow lines={4} />
      </div>
    );
  }

  return (
    <div className="practice-page">
      <h1>{t("student.practice.title")}</h1>
      <p className="practice-subtitle">{t("student.practice.subtitle")}</p>

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
            {(problemsQuery.data?.items ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </details>
      )}

      {problemId === null && (
        <p className="practice-standalone-hint">{t("student.practice.standalone")}</p>
      )}

      {problemId !== null && (
        problemQuery.isLoading ? <SkeletonRow lines={4} /> :
        problemQuery.isError ? <p className="error">{t("student.practice.error")}</p> :
        problemQuery.data && (
          <section className="practice-statement-section" data-testid="practice-statement">
            <SolveStatementPane problem={problemQuery.data} />
          </section>
        )
      )}

      {problemId !== null && (
        <div className="practice-grid">
          <section className="practice-editor-section">
            <h2>{t("solve.editor")}</h2>
            <div className="practice-toolbar">
              <button
                type="button"
                className="primary"
                onClick={handleOpenRunModal}
              >
                {t("student.practice.run")}
                <span className="solve-shortcut-hint" aria-hidden="true">{t("solve.submitShortcut")}</span>
              </button>
              <button type="button" onClick={resetCode}>{t("solve.reset")}</button>
            </div>
            <CodeMirrorEditor value={source} onChange={setSource} />
            <h3 className="practice-h3">Salida de práctica</h3>
            <PracticeOutputPanel
              run={run}
              testCases={casesQuery.data ?? []}
              stdin={stdin}
              stepBudget={problemQuery.data?.step_budget ?? null}
            />
          </section>

          <aside className="practice-runs-section" data-testid="practice-runs">
            <h3>{t("student.practice.runsHistory")}</h3>
            {historyQuery.isLoading ? <SkeletonRow lines={3} /> :
             historyQuery.isError ? <p className="error">{t("student.practice.error")}</p> :
             ((historyQuery.data?.items ?? []).filter(r => r.kind === 'practice')).length === 0 ? <p className="hint">{t("student.practice.noRunsYet")}</p> :
             <table className="datatable my-runs-table">
              <thead>
                <tr>
                  <th>{t("solve.col.when")}</th>
                  <th>{t("solve.col.verdict")}</th>
                  <th>{t("solve.col.time")}</th>
                </tr>
              </thead>
              <tbody>
                 {((historyQuery.data?.items ?? []).filter(r => r.kind === 'practice')).map((r) => (
                  <tr
                    key={r.id}
                    className="my-runs-row"
                    data-testid={`practice-history-${r.id}`}
                    role="button"
                    tabIndex={0}
                    aria-label={`#${r.id}`}
                    onClick={() => {
                      setSelectedHistoryId(r.id);
                      setRunId(r.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedHistoryId(r.id);
                        setRunId(r.id);
                      }
                    }}
                  >
                    <td style={{ textAlign: "left" }}>#{r.id}</td>
                    <td style={{ textAlign: "left" }}>{new Date(r.created_at).toLocaleString()}</td>
                    <td>{r.summary_verdict ? <VerdictBadge verdict={r.summary_verdict} /> : "—"}</td>
                    <td>{r.steps ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            }
          </aside>
        </div>
      )}

      {problemId === null && (
        <div className="practice-grid">
          <section className="practice-editor-section practice-editor-full">
            <h2>{t("solve.editor")}</h2>
            <div className="practice-toolbar">
              <button type="button" className="primary" onClick={handleOpenRunModal}>
                {t("student.practice.run")}
                <span className="solve-shortcut-hint" aria-hidden="true">{t("solve.submitShortcut")}</span>
              </button>
              <button type="button" onClick={resetCode}>{t("solve.reset")}</button>
            </div>
            <CodeMirrorEditor value={source} onChange={setSource} />
            <h3 className="practice-h3">Salida de práctica</h3>
            <PracticeOutputPanel
              run={null}
              testCases={[]}
              stdin={""}
              stepBudget={null}
            />
          </section>
          <aside className="practice-runs-section">
            <h3>{t("student.practice.runsHistory")}</h3>
            <p className="hint">{t("student.practice.outputPlaceholder")}</p>
          </aside>
        </div>
      )}

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
