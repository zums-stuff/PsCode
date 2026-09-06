import { useEffect, useState } from "react";

/**
 * Countdown timer (plan todo 32): ticks every 1s, renders days/hours/minutes/
 * seconds remaining until `targetAt`. When the countdown reaches 0 the
 * optional `onComplete` fires once — the parent uses this to refetch the
 * contest so the status badge / scoreboard react to the phase change
 * (upcoming→running→ended) without a page reload.
 */
export interface CountdownTimerProps {
  /** Target time as ISO string (UTC). */
  targetAt: string;
  /** Called once when the countdown reaches 0. */
  onComplete?: () => void;
}

interface Parts {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  done: boolean;
}

function diffParts(targetMs: number, nowMs: number): Parts {
  const ms = Math.max(0, targetMs - nowMs);
  const totalSec = Math.floor(ms / 1000);
  return {
    days: Math.floor(totalSec / 86_400),
    hours: Math.floor((totalSec % 86_400) / 3_600),
    minutes: Math.floor((totalSec % 3_600) / 60),
    seconds: totalSec % 60,
    done: ms === 0,
  };
}

function format(parts: Parts): string {
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${pad(parts.days)}d ${pad(parts.hours)}h ${pad(parts.minutes)}m ${pad(parts.seconds)}s`;
}

export default function CountdownTimer({
  targetAt,
  onComplete,
}: CountdownTimerProps) {
  const [now, setNow] = useState<number>(() => Date.now());
  const target = new Date(targetAt).getTime();
  const parts = diffParts(target, now);

  useEffect(() => {
    if (parts.done) {
      onComplete?.();
      return;
    }
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [parts.done, onComplete]);

  return (
    <span
      className="countdown-timer"
      data-testid="countdown-timer"
      data-done={parts.done ? "true" : "false"}
    >
      {format(parts)}
    </span>
  );
}
