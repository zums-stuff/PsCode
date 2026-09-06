import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import type {
  Contest,
  ContestParticipant,
  ContestProblem,
  ContestScoreboard as ContestScoreboardData,
  ContestTeam,
} from "../../lib/types";
import ContestStatusBadge, { contestStatus } from "../../components/ContestStatusBadge";
import ContestScoreboard from "../../components/ContestScoreboard";
import ParticipantsPanel from "../../components/ParticipantsPanel";
import PhaseAwareActions from "../../components/PhaseAwareActions";
import ProblemSetEditor from "../../components/ProblemSetEditor";
import TeamsPanel from "../../components/TeamsPanel";

/**
 * /admin/contests/:id — full contest editor: metadata form, problem set,
 * participants, teams (only when enabled), live scoreboard.
 *
 * scoring_mode / teams_enabled become read-only once any done run exists
 * (scoreboard rows) — a contest edit must never change persisted verdicts.
 */
export default function AdminContestDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const contestQuery = useQuery({
    queryKey: ["admin", "contest", id],
    queryFn: () => api.get<Contest>(`/api/contests/${id}`),
  });

  const problemsQuery = useQuery({
    queryKey: ["admin", "contest", id, "problems"],
    queryFn: () =>
      api.get<ContestProblem[]>(`/api/contests/${id}/contest-problems`),
    enabled: contestQuery.data !== undefined,
  });

  const participantsQuery = useQuery({
    queryKey: ["admin", "contest", id, "participants"],
    queryFn: () => api.get<ContestParticipant[]>(`/api/contests/${id}/participants`),
    enabled: contestQuery.data !== undefined,
  });

  const teamsQuery = useQuery({
    queryKey: ["admin", "contest", id, "teams"],
    queryFn: () => api.get<ContestTeam[]>(`/api/contests/${id}/teams`),
    enabled: contestQuery.data?.teams_enabled === true,
  });

  const scoreboardQuery = useQuery({
    queryKey: ["admin", "contest", id, "scoreboard"],
    queryFn: () =>
      api.get<ContestScoreboardData>(`/api/contests/${id}/scoreboard`),
    enabled: contestQuery.data !== undefined,
  });

  if (user?.role === "student") {
    return <Navigate to="/403" replace />;
  }

  if (contestQuery.isLoading) {
    return <p>{t("admin.contests.loading")}</p>;
  }
  if (contestQuery.isError) {
    return <p className="error">{t("admin.contests.error")}</p>;
  }

  const contest = contestQuery.data;
  if (contest === undefined) {
    return <p className="error">{t("admin.contests.notFound")}</p>;
  }

  if (user?.role === "teacher" && contest.created_by !== user.id) {
    return <Navigate to="/403" replace />;
  }

  const phase = contestStatus(contest.start_at, contest.end_at, new Date()).status;
  const hasRuns = (scoreboardQuery.data?.rows.length ?? 0) > 0;

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await api.patch<Contest>(`/api/contests/${id}`, {
        title: title.trim() || (contest?.title ?? ""),
        start_at: startAt ? new Date(startAt).toISOString() : (contest?.start_at ?? ""),
        end_at: endAt ? new Date(endAt).toISOString() : (contest?.end_at ?? ""),
      });
      await queryClient.invalidateQueries({ queryKey: ["admin", "contest", id] });
    } catch {
      setSaveError(t("admin.contests.edit.error"));
    } finally {
      setSaving(false);
    }
  }

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["admin", "contest", id] });
  }

  return (
    <div>
      <h1>
        {contest.title} <ContestStatusBadge startAt={contest.start_at} endAt={contest.end_at} />
      </h1>

      <h2>{t("admin.contests.fields.title")}</h2>
      <div className="form-field">
        <input
          type="text"
          value={title || contest.title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label htmlFor="contest-start">{t("admin.contests.fields.start_at")}</label>
        <input
          id="contest-start"
          type="datetime-local"
          value={startAt || toLocalInput(contest.start_at)}
          onChange={(e) => setStartAt(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label htmlFor="contest-end">{t("admin.contests.fields.end_at")}</label>
        <input
          id="contest-end"
          type="datetime-local"
          value={endAt || toLocalInput(contest.end_at)}
          onChange={(e) => setEndAt(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label>{t("admin.contests.fields.scoring_mode")}</label>
        <select value={contest.scoring_mode} disabled={hasRuns}>
          <option value="cf">{t("admin.contests.scoring.cf")}</option>
          <option value="ioi">{t("admin.contests.scoring.ioi")}</option>
        </select>
      </div>

      <div className="form-field">
        <label>
          <input type="checkbox" checked={contest.teams_enabled} disabled={hasRuns} />{" "}
          {t("admin.contests.fields.teams_enabled")}
        </label>
      </div>

      {hasRuns && <p className="hint">{t("admin.contests.edit.locked")}</p>}
      {saveError && <p className="error">{saveError}</p>}
      <button
        type="button"
        className="primary"
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? t("admin.contests.edit.saving") : t("admin.contests.edit.save")}
      </button>

      <h2>{t("admin.contests.problems")}</h2>
      <ProblemSetEditor
        contestId={contest.id}
        phase={phase}
        problems={problemsQuery.data ?? []}
        onChanged={refresh}
      />

      <h2>{t("admin.contests.participants")}</h2>
      <ParticipantsPanel
        contestId={contest.id}
        phase={phase}
        participants={participantsQuery.data ?? []}
        onChanged={refresh}
      />

      <h2>{t("admin.contests.teams")}</h2>
      {!contest.teams_enabled && <p>{t("admin.contests.teams.hidden")}</p>}
      <TeamsPanel
        contestId={contest.id}
        phase={phase}
        teamsEnabled={contest.teams_enabled}
        teams={teamsQuery.data ?? []}
        onChanged={refresh}
      />

      <h2>{t("admin.contests.scoreboard")}</h2>
      <ContestScoreboard
        contestId={contest.id}
        scoringMode={contest.scoring_mode}
        teamsEnabled={contest.teams_enabled}
        teams={teamsQuery.data ?? []}
        participants={participantsQuery.data ?? []}
      />
    </div>
  );
}

/** datetime-local input value (local time, no seconds) from an ISO string. */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}