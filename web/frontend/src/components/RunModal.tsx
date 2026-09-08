import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { t } from "../lib/i18n";
import type { TestCaseOut } from "../lib/types";

interface RunModalProps {
  problemId: number | null;
  source: string;
  onClose: () => void;
  onRunCreated: (runId: number, stdin: string) => void;
}

/**
 * Practice sandbox modal (plan todo 30): pre-fills a textarea with the
 * problem's is_sample test-case input (editable), then POSTs /api/runs with
 * mode=practice + stdin. Never grades — the run is sandbox-only.
 */
export default function RunModal({
  problemId,
  source,
  onClose,
  onRunCreated,
}: RunModalProps) {
  const [stdin, setStdin] = useState("");
  const [cases, setCases] = useState<TestCaseOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(false);
  const [quotaNotice, setQuotaNotice] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadSample() {
      try {
        const allCases = await api.get<TestCaseOut[]>(
          `/api/problems/${problemId}/cases`,
        );
        if (cancelled) return;
        setCases(allCases);
        const sample = allCases.find((c) => c.is_sample);
        setStdin(sample?.input ?? "");
      } catch {
        if (!cancelled) setLoadError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadSample();
    return () => {
      cancelled = true;
    };
  }, [problemId]);

  async function handleExecute() {
    setSubmitting(true);
    setSubmitError(false);
    setQuotaNotice(false);
    try {
      // Sandbox mode (no problem picked): problem_id is null and the engine
      // runs the source without grading against any cases.  When a problem
      // IS picked the API grades against the problem's test cases as usual.
      const res = await api.post<{ run_id: number }>("/api/runs", {
        problem_id: problemId,
        source,
        mode: "practice",
        stdin,
      });
      onRunCreated(res.run_id, stdin);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setQuotaNotice(true);
      } else {
        setSubmitError(true);
      }
      setSubmitting(false);
    }
  }

  return (
    <div className="run-modal-backdrop" role="presentation">
      <div className="run-modal" role="dialog" aria-modal="true" aria-label={t("solve.run.modal.title")}>
        <h2>{t("solve.run.modal.title")}</h2>
        {loading ? (
          <p className="hint">{t("solve.run.loading")}</p>
        ) : loadError ? (
          <p className="error">{t("solve.run.loadError")}</p>
        ) : (
          <>
            <label htmlFor="run-modal-input">{t("solve.run.modal.inputLabel")}</label>
            <p className="hint">{t("solve.run.modal.inputHint")}</p>
            <textarea
              id="run-modal-input"
              className="run-modal-input"
              value={stdin}
              onChange={(e) => setStdin(e.target.value)}
              rows={6}
              spellCheck={false}
            />
            {cases.length > 1 && (
              <details className="run-modal-cases">
                <summary>{t("solve.run.modal.casesSummary").replace("{count}", String(cases.length))}</summary>
                <table className="run-modal-cases-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t("solve.run.modal.casesInput")}</th>
                      <th>{t("solve.run.modal.casesExpected")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cases.map((c, i) => (
                      <tr key={c.id}>
                        <td>{i + 1}</td>
                        <td><code>{c.input || t("solve.run.modal.casesEmpty")}</code></td>
                        <td><code>{c.expected_output || t("solve.run.modal.casesEmpty")}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
            {quotaNotice && <p className="error">{t("solve.errors.quota")}</p>}
            {submitError && <p className="error">{t("solve.run.submitError")}</p>}
            <div className="run-modal-actions">
              <button
                type="button"
                className="primary"
                onClick={handleExecute}
                disabled={submitting}
              >
                {submitting ? t("solve.run.executing") : t("solve.run.execute")}
              </button>
              <button type="button" onClick={onClose} disabled={submitting}>
                {t("solve.run.cancel")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}