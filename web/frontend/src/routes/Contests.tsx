import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api, listContests } from "../lib/api";
import { t } from "../lib/i18n";
import type { ContestListItem, Page } from "../lib/types";
import ContestStatusBadge, {
  contestStatus,
} from "../components/ContestStatusBadge";
import CountdownTimer from "../components/CountdownTimer";

/**
 * Student contests landing page (plan todo 34). Fetches the full list,
 * groups by status (upcoming / running / ended), and renders cards with
 * countdown timers, register buttons, and enter/view-results links.
 */

function formatDuration(startAt: string, endAt: string): string {
  const ms = new Date(endAt).getTime() - new Date(startAt).getTime();
  const hours = Math.round(ms / 3_600_000);
  return t("student.contests.duration").replace("{hours}", String(hours));
}

function ContestCard({
  contest,
  onRegister,
  registering,
  now,
  onNavigate,
}: {
  contest: ContestListItem;
  onRegister: (id: number) => void;
  registering: boolean;
  now: Date;
  onNavigate: (id: number) => void;
}) {
  const { status } = contestStatus(contest.start_at, contest.end_at, now);
  const duration = formatDuration(contest.start_at, contest.end_at);

  return (
    <div
      className={`contests-index-card contests-index-card--${status}`}
      data-testid={`contest-card-${contest.id}`}
    >
      <div className="contests-index-card-body">
        <div className="contests-index-card-header">
          <button
            type="button"
            className="contests-index-card-title"
            onClick={() => onNavigate(contest.id)}
          >
            {contest.title}
          </button>
          <ContestStatusBadge
            startAt={contest.start_at}
            endAt={contest.end_at}
            now={now}
          />
        </div>
        <div className="contests-index-card-meta">
          <span>{duration}</span>
          <span className="contests-index-card-mode">
            {contest.scoring_mode === "cf"
              ? t("student.contests.cf")
              : t("student.contests.ioi")}
          </span>
          {contest.teams_enabled && (
            <span className="contests-index-card-teams">
              {t("student.contests.teams")}
            </span>
          )}
        </div>
        {status === "upcoming" && (
          <div className="contests-index-card-countdown">
            <span className="contests-index-card-countdown-label">
              {t("student.contests.startsIn")}:
            </span>{" "}
            <CountdownTimer targetAt={contest.start_at} />
          </div>
        )}
        {status === "running" && (
          <div className="contests-index-card-countdown">
            <span className="contests-index-card-countdown-label">
              {t("student.contests.endsIn")}:
            </span>{" "}
            <CountdownTimer targetAt={contest.end_at} />
          </div>
        )}
        {status === "ended" && (
          <div className="contests-index-card-ended">
            {t("student.contests.endedOn")}:{" "}
            {new Date(contest.end_at).toLocaleDateString("es-MX")}
          </div>
        )}
      </div>
      <div className="contests-index-card-actions">
        {status === "upcoming" &&
          (contest.is_registered ? (
            <span className="contests-index-registered-badge" data-testid="registered-badge">
              {t("student.contests.registered")}
            </span>
          ) : (
            <button
              type="button"
              className="primary"
              onClick={() => onRegister(contest.id)}
              disabled={registering}
              data-testid={`register-btn-${contest.id}`}
            >
              {t("student.contests.register")}
            </button>
          ))}
        {status === "running" && (
          <button
            type="button"
            className="primary"
            onClick={() => onNavigate(contest.id)}
            data-testid={`enter-btn-${contest.id}`}
          >
            {t("student.contests.enter")}
          </button>
        )}
        {status === "ended" && (
          <button
            type="button"
            className="primary"
            onClick={() => onNavigate(contest.id)}
            data-testid={`view-results-btn-${contest.id}`}
          >
            {t("student.contests.viewResults")}
          </button>
        )}
      </div>
    </div>
  );
}

function ContestSection({
  title,
  contests,
  onRegister,
  registeringId,
  now,
  onNavigate,
}: {
  title: string;
  contests: ContestListItem[];
  onRegister: (id: number) => void;
  registeringId: number | null;
  now: Date;
  onNavigate: (id: number) => void;
}) {
  return (
    <section className="contests-index-section">
      <h2 className="contests-index-section-title">{title}</h2>
      {contests.length === 0 ? (
        <p className="contests-index-empty">{t("student.contests.empty")}</p>
      ) : (
        <div className="contests-index-list">
          {contests.map((c) => (
            <ContestCard
              key={c.id}
              contest={c}
              onRegister={onRegister}
              registering={registeringId === c.id}
              now={now}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default function Contests() {
  const navigate = useNavigate();
  const [now, setNow] = useState<Date>(() => new Date());
  const [registeringId, setRegisteringId] = useState<number | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);

  // Tick now every 30s for phase transitions.
  useMemo(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["contests"],
    queryFn: () => listContests({ page: 1, size: 100 }),
  });

  const contests = data?.items ?? [];

  const upcoming = useMemo(
    () =>
      contests.filter(
        (c) => contestStatus(c.start_at, c.end_at, now).status === "upcoming",
      ),
    [contests, now],
  );
  const running = useMemo(
    () =>
      contests.filter(
        (c) => contestStatus(c.start_at, c.end_at, now).status === "running",
      ),
    [contests, now],
  );
  const ended = useMemo(
    () =>
      contests.filter(
        (c) => contestStatus(c.start_at, c.end_at, now).status === "ended",
      ),
    [contests, now],
  );

  async function handleRegister(id: number): Promise<void> {
    setRegisteringId(id);
    setRegisterError(null);
    try {
      await api.post(`/api/contests/${id}/register`);
      // Navigate to the contest detail page after successful registration.
      navigate(`/contest/${id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Already registered — treat as success, navigate to contest.
        navigate(`/contest/${id}`);
      } else {
        setRegisterError(t("student.contests.error"));
      }
    } finally {
      setRegisteringId(null);
    }
  }

  if (isLoading) {
    return (
      <div className="contests-index">
        <header className="contests-index-header">
          <h1>{t("student.contests.title")}</h1>
        </header>
        <p className="contests-index-loading">{t("student.contests.loading")}</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="contests-index">
        <header className="contests-index-header">
          <h1>{t("student.contests.title")}</h1>
        </header>
        <p className="error">{t("student.contests.error")}</p>
      </div>
    );
  }

  return (
    <div className="contests-index">
      <header className="contests-index-header">
        <h1>{t("student.contests.title")}</h1>
        <p className="contests-index-subtitle">
          {t("student.contests.subtitle")}
        </p>
      </header>
      {registerError !== null && (
        <p className="error">{registerError}</p>
      )}
      <ContestSection
        title={t("student.contests.running")}
        contests={running}
        onRegister={handleRegister}
        registeringId={registeringId}
        now={now}
        onNavigate={(id) => navigate(`/contest/${id}`)}
      />
      <ContestSection
        title={t("student.contests.upcoming")}
        contests={upcoming}
        onRegister={handleRegister}
        registeringId={registeringId}
        now={now}
        onNavigate={(id) => navigate(`/contest/${id}`)}
      />
      <ContestSection
        title={t("student.contests.ended")}
        contests={ended}
        onRegister={handleRegister}
        registeringId={registeringId}
        now={now}
        onNavigate={(id) => navigate(`/contest/${id}`)}
      />
    </div>
  );
}
