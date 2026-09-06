import { t } from "../lib/i18n";

export interface ContestStatus {
  status: "upcoming" | "running" | "ended";
  label: string;
  color: string;
}

/** Compute contest status from now vs start_at/end_at. */
export function contestStatus(
  startAt: string,
  endAt: string,
  now: Date,
): ContestStatus {
  const start = new Date(startAt).getTime();
  const end = new Date(endAt).getTime();
  const current = now.getTime();
  if (current < start) {
    return {
      status: "upcoming",
      label: t("admin.contests.status.upcoming"),
      color: "gray",
    };
  }
  if (current <= end) {
    return {
      status: "running",
      label: t("admin.contests.status.running"),
      color: "green",
    };
  }
  return {
    status: "ended",
    label: t("admin.contests.status.ended"),
    color: "red",
  };
}

/** Small colored status badge for a contest. */
export default function ContestStatusBadge({
  startAt,
  endAt,
  now = new Date(),
}: {
  startAt: string;
  endAt: string;
  now?: Date;
}) {
  const { label, color } = contestStatus(startAt, endAt, now);
  return (
    <span className={`status-badge status-${color}`} data-testid="contest-status">
      {label}
    </span>
  );
}
