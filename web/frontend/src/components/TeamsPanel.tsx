import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type { ContestTeam } from "../lib/types";
import PhaseAwareActions from "./PhaseAwareActions";

/**
 * Contest teams panel. Renders NOTHING when teams_enabled=false (plan QA:
 * "teams_enabled=false -> team CRUD hidden"). When enabled: list teams,
 * create a team, add a member. Create/add are disabled before the contest
 * starts (PhaseAwareActions).
 */
export default function TeamsPanel({
  contestId,
  phase,
  teamsEnabled,
  teams,
  onChanged,
}: {
  contestId: number;
  phase: string;
  teamsEnabled: boolean;
  teams: ContestTeam[];
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [teamId, setTeamId] = useState("");
  const [memberId, setMemberId] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!teamsEnabled) return null;

  async function handleCreate() {
    if (!name.trim()) return;
    setError(null);
    try {
      await api.post(`/api/contests/${contestId}/teams`, { name: name.trim() });
      setName("");
      onChanged();
    } catch {
      setError(t("admin.contests.teams.createError"));
    }
  }

  async function handleAddMember() {
    if (!teamId || !memberId) return;
    setError(null);
    try {
      await api.post(`/api/contests/${contestId}/teams/${teamId}/members`, {
        user_id: Number(memberId),
      });
      setMemberId("");
      onChanged();
    } catch {
      setError(t("admin.contests.teams.addError"));
    }
  }

  return (
    <div>
      {teams.length === 0 && <p>{t("admin.contests.teams.empty")}</p>}
      {teams.length > 0 && (
        <ul>
          {teams.map((team) => (
            <li key={team.id}>{team.name}</li>
          ))}
        </ul>
      )}
      {error && <p className="error">{error}</p>}
      <div className="form-row">
        <input
          type="text"
          placeholder={t("admin.contests.teams.name")}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <PhaseAwareActions phase={phase}>
          <button
            type="button"
            className="primary"
            onClick={handleCreate}
            disabled={!name.trim()}
          >
            {t("admin.contests.teams.create")}
          </button>
        </PhaseAwareActions>
      </div>
      <div className="form-row">
        <select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
          <option value="">{t("admin.contests.teams.name")}</option>
          {teams.map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </select>
        <input
          type="number"
          placeholder={t("admin.contests.teams.memberId")}
          value={memberId}
          onChange={(e) => setMemberId(e.target.value)}
        />
        <PhaseAwareActions phase={phase}>
          <button
            type="button"
            onClick={handleAddMember}
            disabled={!teamId || !memberId}
          >
            {t("admin.contests.teams.add_member")}
          </button>
        </PhaseAwareActions>
      </div>
    </div>
  );
}
