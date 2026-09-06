/**
 * WebSocket live-results hook (plan todo 27, M8).
 *
 * Connects to `WS /ws/submissions?token=<JWT>[&contest_id=<id>]` and streams
 * run events to the caller. On connect the server replays the last 20 runs
 * (M8) — the hook surfaces those as `events` too, so the UI can resume from
 * history without a separate refetch.
 *
 * Reconnect policy (M8): exponential backoff with jitter, capped; the socket
 * is torn down on logout (token null) and re-established on login. The hook
 * never throws — it exposes `status` so the UI can show a transient
 * "reconnecting" notice without breaking the editor.
 */

import { useEffect, useRef, useState } from "react";
import { useAuth } from "./auth";

export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface RunEvent {
  submission_id: number;
  status: string;
  per_case: {
    case_index: number;
    verdict: string;
    steps: number;
    wall_ms: number;
  }[];
}

const BASE_WS: string =
  (import.meta.env.VITE_WS_URL as string | undefined) ??
  "ws://localhost:8000";

const MAX_BACKOFF_MS = 15_000;
const BASE_BACKOFF_MS = 500;

function backoffDelay(attempt: number): number {
  const exp = Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
  // jitter ±25% to avoid thundering-herd reconnects
  return Math.round(exp * (0.75 + Math.random() * 0.5));
}

/**
 * Subscribe to live run events for the current user.
 *
 * @param contestId optional — observe all runs of a contest (teacher/admin or
 *   contest creator only; the server enforces this, D12).
 * @param enabled set false to keep the socket closed (e.g. not logged in).
 */
export function useRunSocket(
  contestId?: number,
  enabled = true,
): { events: RunEvent[]; status: WsStatus } {
  const { token } = useAuth();
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState<WsStatus>("idle");
  const socketRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled || !token) {
      setStatus("idle");
      socketRef.current?.close();
      socketRef.current = null;
      return;
    }
    const authToken = token;

    let cancelled = false;

    function connect() {
      if (cancelled) return;
      setStatus(attemptRef.current === 0 ? "connecting" : "reconnecting");

      const params = new URLSearchParams({ token: authToken });
      if (contestId !== undefined) params.set("contest_id", String(contestId));
      const ws = new WebSocket(`${BASE_WS}/ws/submissions?${params.toString()}`);
      socketRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setStatus("open");
      };

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(String(msg.data)) as RunEvent;
          setEvents((prev) => [...prev, event]);
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setStatus("closed");
        // schedule reconnect with backoff
        const delay = backoffDelay(attemptRef.current);
        attemptRef.current += 1;
        timerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // onclose follows; nothing to do here
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (timerRef.current !== null) clearTimeout(timerRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [token, contestId, enabled]);

  return { events, status };
}
