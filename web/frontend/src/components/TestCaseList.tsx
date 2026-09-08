import { useState } from "react";
import { t } from "../lib/i18n";
import type { RunDetailCaseOut } from "../lib/types";
import VerdictBadge from "./VerdictBadge";

interface TestCaseListProps {
  cases: RunDetailCaseOut[];
  limit?: number;
  showAllLabel?: string;
}

export default function TestCaseList({
  cases,
  limit,
  showAllLabel,
}: TestCaseListProps) {
  const [expanded, setExpanded] = useState(false);
  const limited = limit !== undefined;
  const visible = !limited || expanded ? cases : cases.slice(0, limit);
  const hasMore = limited && cases.length > limit;

  if (cases.length === 0) return null;

  return (
    <div className="test-case-list">
      <table className="data-table">
        <thead>
          <tr>
            <th>#</th>
            <th>{t("results.columns.input")}</th>
            <th>{t("results.columns.expected")}</th>
            <th>{t("results.columns.verdict")}</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((c) => (
            <tr key={c.case_index}>
              <td>{c.case_index + 1}</td>
              <td>
                <pre className="practice-pre">{c.input ?? "—"}</pre>
              </td>
              <td>
                {c.expected_output === null ? (
                  <span className="hint">{t("submissions.caseHidden")}</span>
                ) : (
                  <pre className="practice-pre">{c.expected_output}</pre>
                )}
              </td>
              <td>
                <VerdictBadge verdict={c.verdict} />
                {c.verdict === "WA" && c.diff_line !== null && (
                  <span className="hint">
                    {" "}({t("results.diffLine")} {c.diff_line})
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && !expanded && (
        <button
          type="button"
          className="link-button"
          onClick={() => setExpanded(true)}
        >
          {showAllLabel ?? t("submissions.showAllCases")}
        </button>
      )}
    </div>
  );
}
