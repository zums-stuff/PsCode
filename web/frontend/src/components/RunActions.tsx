import { useState } from "react";
import { t } from "../lib/i18n";
import type { RunOut } from "../lib/types";

/**
 * Actions cell for the submissions tables (Bug A): every run row gets
 * useful actions instead of a blank column.
 *
 * - done   → "Ver detalle" + "Reenviar" + "Copiar enlace"
 * - failed → "Ver detalle" + "Reintentar" + "Copiar enlace"
 * - queued / running → disabled buttons + "Sin acciones…" hint
 *
 * "Ver detalle" toggles the same inline expansion as clicking the row;
 * "Reenviar"/"Reintentar" re-submit the run's source via onResubmit();
 * "Copiar enlace" copies `/submissions#<id>` to the clipboard.
 */
export default function RunActions({
  run,
  onViewDetail,
  onResubmit,
}: {
  run: RunOut;
  onViewDetail: () => void;
  onResubmit: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const busy = run.status === "queued" || run.status === "running";

  async function copyLink(): Promise<void> {
    const url = `${window.location.origin}/submissions#${run.id}`;
    const ok = await copyText(url);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    }
  }

  const resubmitLabel =
    run.status === "failed" ? t("results.retry") : t("results.resubmit");

  if (busy) {
    return (
      <span className="run-actions" data-testid={`run-actions-${run.id}`}>
        <button type="button" disabled>
          {t("results.viewDetail")}
        </button>
        <button type="button" disabled>
          {resubmitLabel}
        </button>
        <button type="button" disabled>
          {t("results.copyLink")}
        </button>
        <span className="hint">
          {run.status === "queued"
            ? t("results.actionsQueued")
            : t("results.actionsRunning")}
        </span>
      </span>
    );
  }

  return (
    <span className="run-actions" data-testid={`run-actions-${run.id}`}>
      <button
        type="button"
        className="link-button"
        data-testid="run-action-detail"
        onClick={(e) => {
          e.stopPropagation();
          onViewDetail();
        }}
      >
        {t("results.viewDetail")}
      </button>
      <button
        type="button"
        className="link-button"
        data-testid="run-action-resubmit"
        onClick={(e) => {
          e.stopPropagation();
          onResubmit();
        }}
      >
        {resubmitLabel}
      </button>
      <button
        type="button"
        className="link-button"
        data-testid="run-action-copy"
        onClick={(e) => {
          e.stopPropagation();
          void copyLink();
        }}
      >
        {copied ? t("results.copied") : t("results.copyLink")}
      </button>
    </span>
  );
}

function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(
      () => true,
      () => legacyCopy(text),
    );
  }
  return Promise.resolve(legacyCopy(text));
}

function legacyCopy(text: string): boolean {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}