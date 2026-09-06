import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type { ValidateResult } from "../lib/types";

interface RunSampleButtonProps {
  /** The source to validate (statement-editor content). */
  source: string;
}

/**
 * "Run sample" — POST /api/validate (CE check only, no judge run) with the
 * statement content as source; surfaces syntax errors inline.
 */
export default function RunSampleButton({ source }: RunSampleButtonProps) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ValidateResult | null>(null);
  const [failed, setFailed] = useState(false);

  async function run() {
    setRunning(true);
    setFailed(false);
    setResult(null);
    try {
      const res = await api.post<ValidateResult>("/api/validate", { source });
      setResult(res);
    } catch {
      setFailed(true);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="run-sample">
      <button type="button" onClick={run} disabled={running}>
        {running ? t("admin.problem.runSample.running") : t("admin.problem.runSample")}
      </button>
      {failed && <p className="error">{t("admin.problem.runSample.failed")}</p>}
      {result?.ok && <p className="ok">{t("admin.problem.runSample.ok")}</p>}
      {result && !result.ok && result.errors.length > 0 && (
        <div>
          <p className="error">{t("admin.problem.runSample.error")}</p>
          <ul className="error">
            {result.errors.map((e, i) => (
              <li key={i}>
                Línea {e.line}, columna {e.col}: {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}