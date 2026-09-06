import { t } from "../lib/i18n";

/**
 * "Mejor" pill (plan todo 31, M7). Marks the assignment-best run — the run
 * with the highest verdict priority (AC > WA > TLE > RE > CE) per
 * (problem_id, assignment_id), tiebreak by fewest steps. Only meaningful on
 * runs whose assignment_id is set.
 */
export default function BestBadge() {
  return <span className="status-badge status-green">{t("results.best")}</span>;
}
