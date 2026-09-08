import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type {
  ContestParticipant,
  ContestProblem,
  ContestScoreboard,
  ContestScoreboardRow,
  ContestTeam,
} from "../lib/types";

/**
 * Letter for a problem's column index: A..Z, then AA, AB, … (supports
 * contests with more than 26 problems).
 */
export function letterFor(index: number): string {
  let n = index;
  let out = "";
  do {
    out = String.fromCharCode(65 + (n % 26)) + out;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return out;
}

/** solve_time_min → "01:23" (hours:minutes, Codeforces style). */
function formatSolveTime(minutes: number): string {
  const hh = String(Math.floor(minutes / 60)).padStart(2, "0");
  const mm = String(minutes % 60).padStart(2, "0");
  return `${hh}:${mm}`;
}

type ProblemCell = ContestScoreboardRow["problems"][string];

/**
 * Codeforces-style contest scoreboard (Bug B). One column per problem
 * (lettered A/B/C/…), per-cell solve state (+ / +N / -N / empty) with the
 * solve time below, a green/red/grey visual treatment, an "Aceptados /
 * Intentados" footer for CF mode, and per-cell hover tooltips.
 *
 * - cf:  rank, who, penalty (`=`), one cell per problem, total solves.
 * - ioi: rank, who, one points cell per problem, total points.
 *
 * Column list comes from the `problems` prop when provided; otherwise it is
 * derived from the union of problem ids across the scoreboard rows (keeps
 * the component usable with just the /scoreboard response, as the existing
 * admin tests render it).
 */
export default function ContestScoreboard({
  contestId,
  scoringMode,
  teamsEnabled,
  teams,
  participants,
  problems = [],
}: {
  contestId: number;
  scoringMode: string;
  teamsEnabled: boolean;
  teams: ContestTeam[];
  participants: ContestParticipant[];
  problems?: ContestProblem[];
}) {
  const scoreboardQuery = useQuery({
    queryKey: ["admin", "contest", contestId, "scoreboard"],
    queryFn: () =>
      api.get<ContestScoreboard>(`/api/contests/${contestId}/scoreboard`),
  });

  const rows = scoreboardQuery.data?.rows ?? [];

  const orderedProblems = useMemo<ContestProblem[]>(() => {
    const given = [...problems].sort((a, b) => a.order - b.order);
    if (given.length > 0) return given;
    const ids = new Set<string>();
    for (const row of rows) {
      for (const pid of Object.keys(row.problems)) ids.add(pid);
    }
    return [...ids]
      .sort()
      .map((pid, idx) => ({
        contest_id: contestId,
        problem_id: Number(pid),
        order: idx,
        title: "",
      }));
  }, [problems, rows, contestId]);

  const footerCounts = useMemo(() => {
    const counts = new Map<string, { accepted: number; attempted: number }>();
    for (const p of orderedProblems) {
      let accepted = 0;
      let attempted = 0;
      for (const row of rows) {
        const cell = row.problems[String(p.problem_id)];
        if (cell === undefined) continue;
        attempted += 1;
        if (cell.solved) accepted += 1;
      }
      counts.set(String(p.problem_id), { accepted, attempted });
    }
    return counts;
  }, [orderedProblems, rows]);

  if (scoreboardQuery.isLoading) {
    return <p>{t("admin.contests.scoreboard.loading")}</p>;
  }
  if (scoreboardQuery.isError) {
    return <p className="error">{t("admin.contests.scoreboard.error")}</p>;
  }
  if (rows.length === 0) {
    return <p>{t("admin.contests.scoreboard.empty")}</p>;
  }

  const teamName = new Map(teams.map((team) => [String(team.id), team.name]));
  const userName = new Map(
    participants.map((p) => [String(p.user_id), p.username]),
  );

  function participantName(participantId: string): string {
    if (teamsEnabled) return teamName.get(participantId) ?? `#${participantId}`;
    return userName.get(participantId) ?? participantId;
  }

  const isCfoi = scoringMode !== "ioi";

  return (
    <table className="cf-scoreboard" data-testid={`cf-scoreboard-${contestId}`}>
      <thead>
        <tr>
          <th className="cf-rank">#</th>
          <th className="cf-who">{t("admin.contests.scoreboard.participant")}</th>
          {isCfoi && <th className="cf-penalty">=</th>}
          {orderedProblems.map((_, idx) => (
            <th key={letterFor(idx)} className="cf-letter">
              {letterFor(idx)}
            </th>
          ))}
          <th className="cf-total">
            {isCfoi
              ? t("admin.contests.scoreboard.solves")
              : t("admin.contests.scoreboard.total_score")}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.participant_id}>
            <td className="cf-rank">{row.rank}</td>
            <td className="cf-who">{participantName(row.participant_id)}</td>
            {isCfoi && <td className="cf-penalty">{row.penalty}</td>}
            {orderedProblems.map((p) =>
              isCfoi ? (
                <CfCell
                  key={String(p.problem_id)}
                  cell={row.problems[String(p.problem_id)]}
                  dataTestId={`cf-cell-${p.problem_id}`}
                />
              ) : (
                <IoiCell
                  key={String(p.problem_id)}
                  cell={row.problems[String(p.problem_id)]}
                  dataTestId={`cf-cell-${p.problem_id}`}
                />
              ),
            )}
            <td className="cf-total">
              {isCfoi ? row.solves : row.points}
            </td>
          </tr>
        ))}
      </tbody>
      {isCfoi && (
        <tfoot>
          <tr>
            <td colSpan={3} className="cf-footer-label">
              {t("admin.contests.scoreboard.footer")}
            </td>
            {orderedProblems.map((p) => {
              const c = footerCounts.get(String(p.problem_id));
              return (
                <td
                  key={String(p.problem_id)}
                  className="cf-footer-count"
                  data-testid={`cf-footer-${p.problem_id}`}
                >
                  {c?.accepted ?? 0} / {c?.attempted ?? 0}
                </td>
              );
            })}
            <td />
          </tr>
        </tfoot>
      )}
    </table>
  );
}

function CfCell({
  cell,
  dataTestId,
}: {
  cell: ProblemCell | undefined;
  dataTestId: string;
}) {
  if (cell === undefined) {
    return <td className="cf-cell cf-cell--none" data-testid={dataTestId} />;
  }
  if (cell.solved) {
    const attempts = cell.wrong_attempts + 1;
    const tooltip = t("admin.contests.scoreboard.cell.solved")
      .replace("{attempt}", String(attempts))
      .replace("{min}", String(cell.solve_time_min));
    return (
      <td
        className="cf-cell cf-cell--solved"
        data-testid={dataTestId}
        data-status="solved"
        title={tooltip}
      >
        <span className="cf-cell-verdict">
          {cell.wrong_attempts > 0 ? `+${cell.wrong_attempts}` : "+"}
        </span>
        <span className="cf-cell-time">{formatSolveTime(cell.solve_time_min)}</span>
      </td>
    );
  }
  if (cell.wrong_attempts > 0) {
    const tooltip = t("admin.contests.scoreboard.cell.wrong").replace(
      "{count}",
      String(cell.wrong_attempts),
    );
    return (
      <td
        className="cf-cell cf-cell--wrong"
        data-testid={dataTestId}
        data-status="wrong"
        title={tooltip}
      >
        <span className="cf-cell-verdict">-{cell.wrong_attempts}</span>
      </td>
    );
  }
  return <td className="cf-cell cf-cell--none" data-testid={dataTestId} />;
}

function IoiCell({
  cell,
  dataTestId,
}: {
  cell: ProblemCell | undefined;
  dataTestId: string;
}) {
  if (cell === undefined) {
    return <td className="cf-cell cf-cell--none" data-testid={dataTestId} />;
  }
  return (
    <td
      className="cf-cell cf-cell--points"
      data-testid={dataTestId}
      data-status="points"
    >
      {cell.points}
    </td>
  );
}