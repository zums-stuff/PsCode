import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, getContestMyRuns } from "../lib/api";
import { t } from "../lib/i18n";
import { useRunSocket } from "../lib/ws";
import type {
  Contest,
  ContestProblem,
  ContestScoreboard as ContestScoreboardData,
  ContestTeam,
  RunOut,
} from "../lib/types";
import ContestScoreboard from "../components/ContestScoreboard";
import ContestStatusBadge, {
  contestStatus,
} from "../components/ContestStatusBadge";
import CountdownTimer from "../components/CountdownTimer";
import ErrorBoundary from "../components/ErrorBoundary";
import TeamsPanel from "../components/TeamsPanel";
import { useAuth } from "../lib/auth";

/**
 * Student contest page (plan todo 32): header (title, status badge, countdown
 * to start or end), problem list with links to /problem/:id?contest=:id,
 * register button (pre-start only), the live scoreboard (post-start), and the
 * student's own runs in the contest (post-start). The scoreboard is gated by
 * phase (upcoming = never) and by participant access (non-participants get a
 * friendly 403 notice — the backend enforces it).
 *
 * WS hook (useRunSocket) streams the student's own runs; when one of them
 * flips to AC, the scoreboard query is invalidated so the row updates
 * without a reload (M12).
 *
 * The default export is wrapped in an ErrorBoundary so any unhandled render
 * exception shows an "Algo salió mal" message instead of a blank page (see
 * the MyRuns `.items` unpacking below — the bug this boundary guards).
 */
function Contest() {
  const { id } = useParams();
  const contestId = id === undefined ? NaN : Number(id);
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const [now, setNow] = useState<Date>(() => new Date());
  const [registering, setRegistering] = useState<boolean>(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registered, setRegistered] = useState<boolean>(false);

  // Tick `now` every 30s so phase transitions (upcoming→running→ended) react
  // without a full page reload — the CountdownTimer drives sub-second UI.
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const contestQuery = useQuery({
    queryKey: ["contest", contestId],
    queryFn: () => api.get<Contest>(`/api/contests/${contestId}`),
    enabled: !Number.isNaN(contestId),
  });

  const contest = contestQuery.data;

  const phase = useMemo<string | null>(() => {
    if (contest === undefined) return null;
    return contestStatus(contest.start_at, contest.end_at, now).status;
  }, [contest, now]);

  const problemsQuery = useQuery({
    queryKey: ["contest", contestId, "problems"],
    queryFn: () =>
      api.get<ContestProblem[]>(`/api/contests/${contestId}/contest-problems`),
    enabled: contest !== undefined,
  });

  const teamsQuery = useQuery({
    queryKey: ["contest", contestId, "teams"],
    queryFn: () => api.get<ContestTeam[]>(`/api/contests/${contestId}/teams`),
    enabled: contest?.teams_enabled === true,
  });

  // Scoreboard is only meaningful once the contest has started.
  const scoreboardQuery = useQuery({
    queryKey: ["contest", contestId, "scoreboard"],
    queryFn: () =>
      api.get<ContestScoreboardData>(`/api/contests/${contestId}/scoreboard`),
    enabled: phase !== null && phase !== "upcoming",
    retry: false,
  });

  // Students subscribe to their OWN runs (no contest_id observer — that
  // path is teacher/admin-only on the server). On every AC event, refetch
  // the scoreboard so the row updates without a reload (plan M12).
  const { events } = useRunSocket();
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[events.length - 1];
    const hasAc = latest.per_case.some((c) => c.verdict === "AC");
    if (!hasAc) return;
    void queryClient.invalidateQueries({
      queryKey: ["contest", contestId, "scoreboard"],
    });
  }, [events.length, contestId, queryClient]);

  function refresh(): void {
    void queryClient.invalidateQueries({ queryKey: ["contest", contestId] });
    void queryClient.invalidateQueries({
      queryKey: ["contest", contestId, "teams"],
    });
  }

  async function handleRegister(): Promise<void> {
    setRegistering(true);
    setRegisterError(null);
    try {
      await api.post(`/api/contests/${contestId}/register`);
      setRegistered(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Already registered — collapse the button into a confirmation.
        setRegistered(true);
      } else {
        setRegisterError(t("student.contest.registerError"));
      }
    } finally {
      setRegistering(false);
    }
  }

  if (contestQuery.isLoading) {
    return <p>{t("admin.contests.loading")}</p>;
  }
  if (contestQuery.isError || contest === undefined) {
    return <p className="error">{t("admin.contests.notFound")}</p>;
  }

  const problems = problemsQuery.data ?? [];
  const teams = teamsQuery.data ?? [];
  const scoreboardForbidden =
    scoreboardQuery.error instanceof ApiError &&
    scoreboardQuery.error.status === 403;

  return (
    <div className="contest-page">
      {phase === "upcoming" && (
        <div className="contest-hero contest-hero--upcoming" data-testid="contest-hero">
          <h2>{contest.title}</h2>
          <ContestStatusBadge startAt={contest.start_at} endAt={contest.end_at} now={now} />
          <p className="contest-hero-countdown">
            <CountdownTimer targetAt={contest.start_at} onComplete={refresh} />
          </p>
        </div>
      )}
      {phase === "running" && (
        <div className="contest-hero contest-hero--running" data-testid="contest-hero">
          <h2>{contest.title}</h2>
          <ContestStatusBadge startAt={contest.start_at} endAt={contest.end_at} now={now} />
          <p className="contest-hero-countdown">
            <CountdownTimer targetAt={contest.end_at} onComplete={refresh} />
          </p>
        </div>
      )}
      {phase === "ended" && (
        <div className="contest-hero contest-hero--ended" data-testid="contest-hero">
          <h2>{contest.title}</h2>
          <ContestStatusBadge startAt={contest.start_at} endAt={contest.end_at} now={now} />
          <p>{t("student.contests.endedOn")}: {new Date(contest.end_at).toLocaleDateString("es-MX")}</p>
        </div>
      )}

      {phase === null && (
        <header className="contest-header">
          <h1>{contest.title}</h1>
          <ContestStatusBadge startAt={contest.start_at} endAt={contest.end_at} now={now} />
        </header>
      )}

      {phase === "upcoming" && (
        <section className="contest-register">
          {registered ? (
            <p className="ok">
              {t("student.contest.registerAlready")}
            </p>
          ) : (
            <button
              type="button"
              className="primary"
              onClick={() => void handleRegister()}
              disabled={registering}
              data-testid="contest-register"
            >
              {registering
                ? t("student.contest.registering")
                : t("student.contest.register")}
            </button>
          )}
          {registerError !== null && (
            <p className="error">{registerError}</p>
          )}
        </section>
      )}

      <section className="contest-problems">
        <h2>{t("student.contest.problems.title")}</h2>
        {problemsQuery.isLoading && <p>{t("admin.contests.loading")}</p>}
        {!problemsQuery.isLoading && problems.length === 0 && (
          <p className="hint">{t("student.contest.problems.empty")}</p>
        )}
        {problems.length > 0 && (
          <ul className="contest-problem-list">
            {problems.map((p) => (
              <li key={p.problem_id} data-testid={`contest-problem-${p.problem_id}`}>
                <Link to={`/problem/${p.problem_id}?contest=${contestId}`}>
                  #{p.order + 1} {p.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {phase !== "upcoming" && (
        <section className="contest-scoreboard">
          <h2>{t("student.contest.scoreboard.title")}</h2>
          {scoreboardQuery.isLoading && (
            <p>{t("admin.contests.scoreboard.loading")}</p>
          )}
          {scoreboardForbidden && (
            <p className="hint" data-testid="scoreboard-forbidden">
              {t("student.contest.scoreboard.forbidden")}
            </p>
          )}
          {scoreboardQuery.data !== undefined && (
            <ContestScoreboard
              contestId={contestId}
              scoringMode={contest.scoring_mode}
              teamsEnabled={contest.teams_enabled}
              teams={teams}
              problems={problems}
              // Students don't fetch the participants roster (backend is
              // teacher/admin-only); names fall back to raw participant_id.
              participants={[]}
            />
          )}
        </section>
      )}

      {contest.teams_enabled && (
        <section className="contest-teams">
          <h2>{t("student.contest.teams.title")}</h2>
          <TeamsPanel
            contestId={contestId}
            phase={phase ?? ""}
            teamsEnabled={contest.teams_enabled}
            onChanged={refresh}
          />
        </section>
      )}

      {phase !== "upcoming" && (
        <section className="contest-my-runs">
          <h2>{t("results.title")}</h2>
          <MyRuns contestId={contestId} />
        </section>
      )}
    </div>
  );
}

function MyRuns({ contestId }: { contestId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["contest", contestId, "my-runs"],
    queryFn: () => getContestMyRuns(contestId),
  });

  // The API returns a paginated Page<RunOut> (`{items, ...}`), not a bare
  // array.  Reading `data.items` (defaulting to []) prevents the
  // `TypeError: data.map is not a function` that blanked the contest page —
  // the root cause of this bug (see api.getContestMyRuns).
  const runs = data?.items ?? [];

  if (isLoading) return <p>{t("results.loading")}</p>;
  if (isError) return <p className="error">{t("results.loadError")}</p>;
  if (runs.length === 0) return <p className="hint">{t("results.empty")}</p>;

  return (
    <table>
      <thead>
        <tr>
          <th>{t("results.columns.problem")}</th>
          <th>{t("results.columns.verdict")}</th>
          <th>{t("results.columns.steps")}</th>
          <th>{t("results.columns.wall")}</th>
          <th>{t("results.columns.submitted")}</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr key={run.id}>
            <td>{run.problem_id}</td>
            <td>{run.summary_verdict ?? "—"}</td>
            <td>{run.steps ?? "—"}</td>
            <td>{run.wall_ms !== null ? `${run.wall_ms}ms` : "—"}</td>
            <td>{new Date(run.created_at).toLocaleString("es-MX")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Wrap the page in an ErrorBoundary (contest page fix): any unhandled
// render exception now shows "Algo salió mal" instead of a blank page.
export default function ContestPage() {
  return (
    <ErrorBoundary>
      <Contest />
    </ErrorBoundary>
  );
}
