import { t } from "../lib/i18n";

export type Verdict =
  | "AC"
  | "WA"
  | "TLE"
  | "RE"
  | "CE"
  | "QUEUED"
  | "RUNNING"
  | "DONE"
  | "FAILED"
  | string;

function verdictClass(verdict: string): string {
  switch (verdict) {
    case "AC":
      return "status-green";
    case "WA":
      return "status-red";
    case "TLE":
      return "status-yellow";
    case "RE":
      return "status-orange";
    case "CE":
      return "status-purple";
    case "DONE":
      return "status-green";
    case "FAILED":
      return "status-red";
    case "QUEUED":
    case "RUNNING":
      return "status-gray";
    default:
      return "status-gray";
  }
}

/**
 * Colored verdict pill (plan todo 31). Accepts AC/WA/TLE/RE/CE (verdict) or
 * QUEUED/RUNNING/DONE/FAILED (run status). Uses the .status-* classes defined
 * in styles.css.
 */
export default function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span className={`status-badge ${verdictClass(verdict)}`}>{verdict}</span>
  );
}

/** Convenience for places that need to render the localized run-status label. */
export function RunStatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge ${verdictClass(status)}`}>
      {t(`results.status.${status}`)}
    </span>
  );
}
