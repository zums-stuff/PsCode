import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, listForumThreads } from "../lib/api";
import { useAuth } from "../lib/auth";
import { t } from "../lib/i18n";
import type { ForumThread, ProblemOut } from "../lib/types";
import NewThreadForm from "../components/NewThreadForm";
import ThreadDetail from "../components/ThreadDetail";
import ThreadList from "../components/ThreadList";

const PAGE_SIZE = 10;

/**
 * Per-problem forum page (plan todo 33). Renders the thread list with a
 * client-side paginator and a "new thread" button. Selecting a thread swaps
 * in ThreadDetail with a back button. Real-account requirement: only
 * authenticated users see the form; the auth guard is enforced by App.tsx
 * (RequireAuth wraps the route). No anonymous / private-message flow.
 */
export default function Forum() {
  const { id } = useParams();
  const problemId = Number(id);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<ForumThread | null>(null);
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const problemQuery = useQuery({
    queryKey: ["problem", problemId],
    queryFn: () => api.get<ProblemOut>(`/api/problems/${problemId}`),
    enabled: Number.isFinite(problemId),
  });

  const threadsQuery = useQuery({
    queryKey: ["forum", "threads", problemId],
    queryFn: () => listForumThreads(problemId),
    enabled: Number.isFinite(problemId),
  });

  if (!Number.isFinite(problemId)) {
    return <p className="error">{t("forum.loadError")}</p>;
  }

  if (problemQuery.isLoading || threadsQuery.isLoading) {
    return <p>{t("forum.loading")}</p>;
  }

  if (problemQuery.isError || threadsQuery.isError) {
    return <p className="error">{t("forum.loadError")}</p>;
  }

  const problem = problemQuery.data;
  const threads = threadsQuery.data ?? [];

  return (
    <div className="forum-page" data-testid="forum-page">
      <h1>
        {t("forum.title")}
        {problem !== undefined ? ` — ${problem.title}` : ""}
      </h1>

      {selected !== null ? (
        <ThreadDetail
          threadId={selected.id}
          threadPinned={selected.pinned}
          user={user}
          onBack={() => setSelected(null)}
        />
      ) : (
        <>
          {toast !== null && (
            <p className="error" data-testid="forum-toast" role="alert">
              {toast}
            </p>
          )}
          <div className="forum-actions">
            <button
              type="button"
              className="primary"
              onClick={() => setCreating((v) => !v)}
              data-testid="new-thread-toggle"
            >
              {creating ? t("forum.threads.cancelNew") : t("forum.threads.new")}
            </button>
          </div>
          {creating && (
            <NewThreadForm
              problemId={problemId}
              onCancel={() => setCreating(false)}
              onCreated={(thread) => {
                setCreating(false);
                setSelected(thread);
                void queryClient.invalidateQueries({
                  queryKey: ["forum", "threads", problemId],
                });
              }}
              onError={(err) => {
                if (err instanceof ApiError && err.status === 403) {
                  setToast(t("forum.thread.contestLockToast"));
                }
              }}
            />
          )}
          <ThreadList
            threads={threads}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
            onSelect={(thread) => setSelected(thread)}
          />
        </>
      )}
    </div>
  );
}
