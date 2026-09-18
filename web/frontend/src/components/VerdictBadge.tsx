import { t } from "../lib/i18n";
import { verdictColorClass, verdictFallbackClass } from "../lib/verdict";

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

export default function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span className={`status-badge ${verdictFallbackClass(verdict)} ${verdictColorClass(verdict)}`}>
      {verdict}
    </span>
  );
}

export function RunStatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge ${verdictFallbackClass(status)} ${verdictColorClass(status)}`}>
      {t(`results.status.${status}`)}
    </span>
  );
}
