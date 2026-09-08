import { useState } from "react";
import { ApiError, createForumThread } from "../lib/api";
import { t } from "../lib/i18n";
import type { ForumThread } from "../lib/types";

interface NewThreadFormProps {
  problemId: number;
  onCreated: (thread: ForumThread) => void;
  onCancel: () => void;
  /** Optional notification for failed POSTs (e.g. surfacing the 403 toast). */
  onError?: (err: unknown) => void;
}

/**
 * New-thread composer (todo 33). Posts title + body to the API; the server
 * owns the phase-lock check and returns 403 if the problem is in a live
 * contest window and the author is not a teacher — surfaced as an inline
 * error so the user gets a clear message (D15 + M9).
 */
export default function NewThreadForm({
  problemId,
  onCreated,
  onCancel,
  onError,
}: NewThreadFormProps) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (title.trim().length === 0 || body.trim().length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const thread = await createForumThread(problemId, title.trim(), body);
      onCreated(thread);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("forum.thread.contestLock"));
      } else {
        setError(t("forum.thread.createError"));
      }
      onError?.(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="forum-new-thread"
      onSubmit={handleSubmit}
      data-testid="new-thread-form"
    >
      <h2>{t("forum.threads.new")}</h2>
      <div className="form-field">
        <label htmlFor="new-thread-title">{t("forum.thread.newTitle")}</label>
        <input
          id="new-thread-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          maxLength={200}
        />
      </div>
      <div className="form-field">
        <label htmlFor="new-thread-body">{t("forum.thread.body")}</label>
        <textarea
          id="new-thread-body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          required
          rows={4}
        />
      </div>
      {error !== null && (
        <p className="error" data-testid="new-thread-error">
          {error}
        </p>
      )}
      <div className="form-row">
        <button
          type="submit"
          className="primary"
          disabled={submitting}
          data-testid="new-thread-submit"
        >
          {submitting ? t("forum.thread.creating") : t("forum.thread.create")}
        </button>
        <button type="button" onClick={onCancel} disabled={submitting}>
          {t("forum.threads.cancelNew")}
        </button>
      </div>
    </form>
  );
}
