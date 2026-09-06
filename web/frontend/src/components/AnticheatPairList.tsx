import type { AnticheatPair } from "../lib/types";
import { downloadCSV, toCSV } from "../lib/csv";
import { t } from "../lib/i18n";

interface AnticheatPairListProps {
  pairs: AnticheatPair[];
  /** Effective threshold used by the current query — pairs < threshold are filtered out server-side. */
  threshold: number;
  /** Whether same-team exclusion applies for this scope (contest + teams_enabled). */
  sameTeamExclusion: boolean;
  loading: boolean;
  error: string | null;
  /** Fired when the teacher clicks "Ver diff" on a row. */
  onSelectPair: (pair: AnticheatPair) => void;
  /** Id of the pair currently expanded in the diff viewer. */
  selectedPairKey: string | null;
}

/**
 * Pairs table for /admin/anticheat (todo 25).
 *
 * Server already excludes same-team pairs (M12, scope=contest with
 * teams_enabled).  The component renders an empty-state hint when no
 * pairs come back, plus a CSV-export action that downloads the rows
 * currently on screen.
 */
export default function AnticheatPairList({
  pairs,
  threshold,
  sameTeamExclusion,
  loading,
  error,
  onSelectPair,
  selectedPairKey,
}: AnticheatPairListProps) {
  function pairKey(pair: AnticheatPair): string {
    return `${pair.run_a_id}-${pair.run_b_id}`;
  }

  function handleExport() {
    const header = [
      "run_a_id",
      "user_a",
      "run_b_id",
      "user_b",
      "score",
      "flagged",
    ];
    const rows: (string | number)[][] = [
      header,
      ...sortedPairs.map((p) => [
        p.run_a_id,
        p.user_a_username,
        p.run_b_id,
        p.user_b_username,
        p.score.toFixed(4),
        p.flagged ? "true" : "false",
      ]),
    ];
    const csv = toCSV(rows);
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    downloadCSV(`anticheat-${stamp}.csv`, csv);
  }

  if (loading) {
    return <p>{t("admin.anticheat.pairs.loading")}</p>;
  }

  if (error !== null) {
    return <p className="error">{error}</p>;
  }

  /** Server returns score-desc (todo 39), but we re-sort defensively so a
   *  future API regression doesn't break the UI contract. */
  const sortedPairs = pairs
    .slice()
    .sort((a, b) => b.score - a.score || a.run_a_id - b.run_a_id);

  return (
    <section className="anticheat-pair-list">
      <header className="anticheat-pair-list-header">
        <h2>{t("admin.anticheat.pairs.title")}</h2>
        <button
          type="button"
          onClick={handleExport}
          disabled={pairs.length === 0}
        >
          {t("admin.anticheat.pairs.export")}
        </button>
      </header>

      {sameTeamExclusion && (
        <p className="hint">{t("admin.anticheat.pairs.sameTeamHint")}</p>
      )}

      {pairs.length === 0 ? (
        <p>
          {threshold > 0
            ? t("admin.anticheat.pairs.emptyThreshold")
            : t("admin.anticheat.pairs.empty")}
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{t("admin.anticheat.pairs.columns.runA")}</th>
              <th>{t("admin.anticheat.pairs.columns.runB")}</th>
              <th>{t("admin.anticheat.pairs.columns.score")}</th>
              <th>{t("admin.anticheat.pairs.columns.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {sortedPairs.map((pair) => {
              const key = pairKey(pair);
              const isSelected = key === selectedPairKey;
              return (
                <tr key={key} data-testid={`pair-row-${key}`}>
                  <td>
                    #{pair.run_a_id}{" "}
                    <span className="hint">({pair.user_a_username})</span>
                  </td>
                  <td>
                    #{pair.run_b_id}{" "}
                    <span className="hint">({pair.user_b_username})</span>
                  </td>
                  <td>{pair.score.toFixed(4)}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => onSelectPair(pair)}
                      aria-pressed={isSelected}
                    >
                      {isSelected
                        ? t("admin.anticheat.pairs.hideDiff")
                        : t("admin.anticheat.pairs.viewDiff")}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
