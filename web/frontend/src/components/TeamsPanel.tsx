import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import { useAuth } from "../lib/auth";
import type { ContestParticipant, ContestTeam } from "../lib/types";
import PhaseAwareActions from "./PhaseAwareActions";
import CreateTeamModal from "./CreateTeamModal";

/**
 * Contest teams panel (teams mode fix).
 *
 * Renders NOTHING when teams_enabled=false (plan QA: "teams_enabled=false ->
 * team CRUD hidden"). When enabled:
 *  - Teachers/admins: list teams (name + member count + members), create a
 *    team (modal), add a member (student picker). Team creation/add are
 *    disabled before the contest starts (PhaseAwareActions).
 *  - Students: show "Mi equipo: <name>" when in a team, otherwise a
 *    "No estás en un equipo todavía" notice.
 *
 * Teams are self-fetched from GET /api/contests/{id}/teams on mount and
 * refetched after any create/add (teams now carry ``members``). onChanged()
 * lets a parent (e.g. the admin/student detail pages) refresh their own
 * team list too — that keeps the scoreboard's team-name map in sync.
 *
 * The backend (todo 24) supports create-team and add-member only — there are
 * NO remove-member / delete-team endpoints, so those actions are intentionally
 * not offered here (see the unsupported note).
 */
export default function TeamsPanel({
  contestId,
  phase,
  teamsEnabled,
  onChanged = () => {},
}: {
  contestId: number;
  phase: string;
  teamsEnabled: boolean;
  onChanged?: () => void;
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  // add-member state: which team + selected participant
  const [addTeamId, setAddTeamId] = useState<number | null>(null);
  const [memberId, setMemberId] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [participants, setParticipants] = useState<ContestParticipant[]>([]);
  const [loadingParticipants, setLoadingParticipants] = useState(false);

  const teamsQuery = useQuery({
    queryKey: ["teams", contestId],
    queryFn: () => api.get<ContestTeam[]>(`/api/contests/${contestId}/teams`),
    enabled: teamsEnabled,
  });

  if (!teamsEnabled) return null;

  const isStaff = user?.role === "teacher" || user?.role === "admin";
  const userId = user?.id;
  const teams = teamsQuery.data ?? [];

  function refresh(): void {
    void queryClient.invalidateQueries({ queryKey: ["teams", contestId] });
    onChanged();
  }

  // Student view: just their own team membership.
  if (!isStaff) {
    const myTeam = teams.find((team) => team.members.includes(userId ?? -1));
    return (
      <div className="teams-my">
        {myTeam ? (
          <p className="ok" data-testid="my-team">
            {t("student.contest.teams.mine")} {myTeam.name}
          </p>
        ) : (
          <p className="hint" data-testid="no-team">
            {t("student.contest.teams.noTeam")}
          </p>
        )}
      </div>
    );
  }

  function openAddMember(teamId: number) {
    setAddTeamId(teamId);
    setMemberId("");
    setError(null);
    if (participants.length === 0) {
      setLoadingParticipants(true);
      api
        .get<ContestParticipant[]>(`/api/contests/${contestId}/participants`)
        .then((data) => setParticipants(data))
        .catch(() => setError(t("admin.contests.teams.addError")))
        .finally(() => setLoadingParticipants(false));
    }
  }

  async function handleAddMember() {
    if (addTeamId === null || !memberId) return;
    setAdding(true);
    setError(null);
    try {
      await api.post(
        `/api/contests/${contestId}/teams/${addTeamId}/members`,
        { user_id: Number(memberId) },
      );
      setMemberId("");
      setAddTeamId(null);
      refresh();
    } catch {
      setError(t("admin.contests.teams.addError"));
    } finally {
      setAdding(false);
    }
  }

  return (
    <div data-testid="teams-panel">
      {error && <p className="error">{error}</p>}

      <p className="hint">{t("admin.contests.teams.createVisible")}</p>

      {teamsQuery.isLoading && <p>{t("admin.contests.loading")}</p>}
      {!teamsQuery.isLoading && teams.length === 0 && (
        <p>{t("admin.contests.teams.empty")}</p>
      )}
      {teams.length > 0 && (
        <ul className="teams-list">
          {teams.map((team) => (
            <li key={team.id} className="team-item" data-testid={`team-${team.id}`}>
              <div className="team-header">
                <strong>{team.name}</strong>
                <span className="team-count">
                  {team.members.length}{" "}
                  {team.members.length === 1
                    ? t("admin.contests.teams.member")
                    : t("admin.contests.teams.members")}
                </span>
              </div>
              {team.members.length > 0 ? (
                <ul className="team-members">
                  {team.members.map((m) => (
                    <li key={m} data-testid={`team-member-${m}`}>
                      #{m}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="hint">{t("admin.contests.teams.noMembers")}</p>
              )}
              <div className="form-row team-add-member">
                {addTeamId === team.id ? (
                  <>
                    <select
                      data-testid={`member-select-${team.id}`}
                      value={memberId}
                      onChange={(e) => setMemberId(e.target.value)}
                      disabled={loadingParticipants}
                    >
                      <option value="">
                        {loadingParticipants
                          ? t("admin.contests.loading")
                          : t("admin.contests.teams.chooseStudent")}
                      </option>
                      {participants
                        .filter((p) => !team.members.includes(p.user_id))
                        .map((p) => (
                          <option key={p.user_id} value={p.user_id}>
                            {p.username} (#{p.user_id})
                          </option>
                        ))}
                    </select>
                    <button
                      type="button"
                      className="primary"
                      data-testid={`add-member-${team.id}`}
                      onClick={() => void handleAddMember()}
                      disabled={!memberId || adding}
                    >
                      {t("student.contest.teams.addMemberButton")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setAddTeamId(null)}
                      disabled={adding}
                    >
                      {t("admin.contests.teams.modal.cancel")}
                    </button>
                  </>
                ) : (
                  <PhaseAwareActions phase={phase}>
                    <button
                      type="button"
                      onClick={() => openAddMember(team.id)}
                      data-testid={`open-add-member-${team.id}`}
                    >
                      {t("admin.contests.teams.add_member")}
                    </button>
                  </PhaseAwareActions>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="form-row">
        <PhaseAwareActions phase={phase}>
          <button
            type="button"
            className="primary"
            onClick={() => setShowCreate(true)}
            data-testid="open-create-team"
          >
            {t("admin.contests.teams.create")}
          </button>
        </PhaseAwareActions>
      </div>

      <p className="hint">{t("admin.contests.teams.unsupportedNote")}</p>

      {showCreate && (
        <CreateTeamModal
          contestId={contestId}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}
