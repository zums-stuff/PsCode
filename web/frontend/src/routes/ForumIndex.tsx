import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError, createThread, listAllThreads } from "../lib/api";
import { t } from "../lib/i18n";
import type { Page, ProblemListItem, ThreadIndexItem } from "../lib/types";

const PAGE_SIZE = 20;

/**
 * Forums landing page (forums tab) at /forum.
 *
 * Shows a flat list of every thread the student can see across the problems
 * in their classes (and public problems), with a "new thread" modal.  A FLAT
 * list (not grouped by problem) is used because the row already carries the
 * problem title + link, and grouping would add visual noise for the typical
 * low thread volume; pinned threads float to the top, then by recency.
 *
 * Clicking a row navigates to /forum/problem/{problem_id}, where the
 * existing per-problem <Forum /> page shows the full thread list for that
 * problem and the thread detail view (with replies).
 */
export default function ForumIndex() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);

  const threadsQuery = useQuery({
    queryKey: ["forum", "index", page],
    queryFn: () => listAllThreads({ page, size: PAGE_SIZE }),
  });

  const problemsQuery = useQuery({
    queryKey: ["forum", "index", "problems"],
    queryFn: () =>
      api.get<Page<ProblemListItem>>("/api/problems?page=1&size=100"),
    enabled: modalOpen,
  });

  if (threadsQuery.isLoading) {
    return <p>{t("student.forum.index.loading")}</p>;
  }
  if (threadsQuery.isError) {
    return (
      <div>
        <p className="error">{t("student.forum.index.error")}</p>
        <button type="button" onClick={() => void queryClient.invalidateQueries({ queryKey: ["forum", "index"] })}>
          {t("student.forum.index.retry")}
        </button>
      </div>
    );
  }

  const data = threadsQuery.data ?? emptyPage;
  const threads = data.items ?? [];

  return (
    <div className="forum-index" data-testid="forum-index">
      <header className="forum-index-header">
        <h1>{t("student.forum.index.title")}</h1>
        <p className="hint">{t("student.forum.index.subtitle")}</p>
        <div className="forum-index-actions">
          <button
            type="button"
            className="primary"
            onClick={() => setModalOpen(true)}
            data-testid="forum-index-new"
          >
            {t("student.forum.index.newThread")}
          </button>
        </div>
      </header>

      {threads.length === 0 ? (
        <p className="forum-index-empty" data-testid="forum-index-empty">
          {t("student.forum.index.empty")}
        </p>
      ) : (
        <ul className="forum-index-list" data-testid="forum-index-list">
          {threads.map((thread) => (
            <li key={thread.id} className="forum-index-row" data-testid={`forum-index-row-${thread.id}`}>
              <Link
                to={`/forum/problem/${thread.problem_id}`}
                className="forum-index-row-main"
                data-testid={`forum-index-thread-${thread.id}`}
              >
                <span className="forum-index-row-title">
                  {thread.pinned && (
                    <span className="forum-pinned-badge">{t("forum.thread.pinned")}</span>
                  )}{" "}
                  {thread.title}
                </span>
                <span className="forum-index-row-meta">
                  <span className="forum-index-problem">{t("student.forum.index.problem")}: {thread.problem_title}</span>
                  <span className="forum-index-author">{author(thread.author_username)}</span>
                  <span className="forum-index-created">{t("student.forum.index.createdAt")}: {formatDate(thread.created_at)}</span>
                  <span className="forum-index-activity">
                    {t("student.forum.index.lastActivity")}:{" "}
                    {thread.last_activity_at ? formatDate(thread.last_activity_at) : "—"}
                  </span>
                </span>
              </Link>
              <span
                className={`forum-index-replies ${thread.reply_count > 0 ? "has-replies" : ""}`}
                data-testid={`forum-index-replies-${thread.id}`}
              >
                {replies(thread.reply_count)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {data.total > PAGE_SIZE && (
        <div className="forum-index-pagination">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            data-testid="forum-index-prev"
          >
            {t("forum.pagination.prev")}
          </button>
          <span>
            {t("forum.pagination.label")} {data.page} / {Math.max(1, Math.ceil(data.total / PAGE_SIZE))}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= Math.ceil(data.total / PAGE_SIZE)}
            data-testid="forum-index-next"
          >
            {t("forum.pagination.next")}
          </button>
        </div>
      )}

      {modalOpen && (
        <NewThreadModal
          problems={problemsQuery.data?.items ?? []}
          loading={problemsQuery.isLoading}
          onClose={() => setModalOpen(false)}
          onCreated={() => {
            setModalOpen(false);
            void queryClient.invalidateQueries({ queryKey: ["forum", "index"] });
          }}
        />
      )}
    </div>
  );
}

const emptyPage: Page<ThreadIndexItem> = { items: [], page: 1, size: PAGE_SIZE, total: 0 };

function replies(count: number): string {
  return count > 0
    ? t("student.forum.index.replies").replace("{count}", String(count))
    : t("student.forum.index.noReplies");
}

function author(name: string): string {
  return t("student.forum.index.author").replace("{name}", name);
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

interface NewThreadModalProps {
  problems: ProblemListItem[];
  loading: boolean;
  onClose: () => void;
  onCreated: () => void;
}

/**
 * Modal composer for a new top-level thread.  Demands a problem (from a
 * <select> of the accessible problems), title and body.  Empty title/body is
 * rejected client-side before the POST; the server's 403 contest-phase lock
 * is surfaced as an inline error.
 */
function NewThreadModal({ problems, loading, onClose, onCreated }: NewThreadModalProps) {
  const queryClient = useQueryClient();
  const [problemId, setProblemId] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => createThread(Number(problemId), title.trim(), body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["forum", "index"] });
      onCreated();
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("student.forum.index.modal.contestLock"));
      } else {
        setError(t("student.forum.index.modal.error"));
      }
    },
  });

  function validate(): string | null {
    if (problemId === "") return t("student.forum.index.modal.validateTitle");
    if (title.trim().length === 0) return t("student.forum.index.modal.validateTitle");
    if (body.trim().length === 0) return t("student.forum.index.modal.validateBody");
    return null;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const problem = validate();
    if (problem !== null) {
      setError(problem);
      return;
    }
    setError(null);
    createMutation.mutate();
  }

  return (
    <div className="forum-index-backdrop" data-testid="forum-index-modal" onClick={onClose}>
      <form
        className="forum-index-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        data-testid="forum-index-new-form"
        noValidate
      >
        <h2>{t("student.forum.index.modal.title")}</h2>
        <div className="form-field">
          <label htmlFor="forum-index-problem">{t("student.forum.index.modal.problem")}</label>
          <select
            id="forum-index-problem"
            value={problemId}
            onChange={(e) => setProblemId(e.target.value)}
            data-testid="forum-index-problem-select"
            disabled={loading}
          >
            <option value="">{t("student.forum.index.modal.selectProblem")}</option>
            {problems.map((p) => (
              <option key={p.id} value={p.id}>
                #{p.id} — {p.title}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="forum-index-title">{t("student.forum.index.modal.titleField")}</label>
          <input
            id="forum-index-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            data-testid="forum-index-title"
          />
        </div>
        <div className="form-field">
          <label htmlFor="forum-index-body">{t("student.forum.index.modal.body")}</label>
          <textarea
            id="forum-index-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={4}
            data-testid="forum-index-body"
          />
        </div>
        {error !== null && (
          <p className="error" data-testid="forum-index-modal-error">
            {error}
          </p>
        )}
        <div className="form-row">
          <button
            type="submit"
            className="primary"
            disabled={createMutation.isPending}
            data-testid="forum-index-modal-submit"
          >
            {createMutation.isPending
              ? t("student.forum.index.modal.submitting")
              : t("student.forum.index.modal.submit")}
          </button>
          <button type="button" onClick={onClose} disabled={createMutation.isPending}>
            {t("student.forum.index.modal.cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}
