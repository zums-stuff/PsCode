import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type {
  ContestParticipant,
  ContestScoreboard,
  ContestTeam,
} from "../lib/types";

/**
 * Contest scoreboard renderer. Switches shape on scoring_mode:
 * - cf:  rank, participant, solves, penalty (sorted solves desc, penalty asc)
 * - ioi: rank, participant, total_score, max_case_score (sorted total desc)
 * When teams_enabled, rows are teams (participant_id = team id) and the
 * participant column shows the team name; otherwise rows are users and the
 * column shows the username.
 */
export default function ContestScoreboard({
  contestId,
  scoringMode,
  teamsEnabled,
  teams,
  participants,
}: {
  contestId: number;
  scoringMode: string;
  teamsEnabled: boolean;
  teams: ContestTeam[];
  participants: ContestParticipant[];
}) {
  const scoreboardQuery = useQuery({
    queryKey: ["admin", "contest", contestId, "scoreboard"],
    queryFn: () =>
      api.get<ContestScoreboard>(`/api/contests/${contestId}/scoreboard`),
  });

  if (scoreboardQuery.isLoading) {
    return <p>{t("admin.contests.scoreboard.loading")}</p>;
  }
  if (scoreboardQuery.isError) {
    return <p className="error">{t("admin.contests.scoreboard.error")}</p>;
  }

  const rows = scoreboardQuery.data?.rows ?? [];
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

  if (scoringMode === "ioi") {
    return (
      <table>
        <thead>
          <tr>
            <th>{t("admin.contests.scoreboard.rank")}</th>
            <th>{t("admin.contests.scoreboard.participant")}</th>
            <th>{t("admin.contests.scoreboard.total_score")}</th>
            <th>{t("admin.contests.scoreboard.max_case")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.participant_id}>
              <td>{row.rank}</td>
              <td>{participantName(row.participant_id)}</td>
              <td>{row.points}</td>
              <td>{row.total_ac_cases}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>{t("admin.contests.scoreboard.rank")}</th>
          <th>{t("admin.contests.scoreboard.participant")}</th>
          <th>{t("admin.contests.scoreboard.solves")}</th>
          <th>{t("admin.contests.scoreboard.penalty")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.participant_id}>
            <td>{row.rank}</td>
            <td>{participantName(row.participant_id)}</td>
            <td>{row.solves}</td>
            <td>{row.penalty}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
