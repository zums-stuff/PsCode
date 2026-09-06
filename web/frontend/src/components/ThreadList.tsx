import type { ForumThread } from "../lib/types";
import { t } from "../lib/i18n";

interface ThreadListProps {
  threads: ForumThread[];
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onSelect: (thread: ForumThread) => void;
  selectedThreadId?: number;
}

/**
 * Per-problem thread list (todo 33). Renders rows with pinned first, then by
 * recency. Client-side pagination: pageSize rows per page; navigation keeps
 * selection in the parent route (page state lives in Forum.tsx).
 */
export default function ThreadList({
  threads,
  page,
  pageSize,
  onPageChange,
  onSelect,
  selectedThreadId,
}: ThreadListProps) {
  if (threads.length === 0) {
    return <p className="forum-empty">{t("forum.threads.empty")}</p>;
  }

  const sorted = [...threads].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    return b.created_at.localeCompare(a.created_at);
  });
  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  const visible = sorted.slice(start, start + pageSize);

  return (
    <div className="forum-thread-list">
      <ul>
        {visible.map((thread) => (
          <li
            key={thread.id}
            className={
              thread.id === selectedThreadId ? "forum-thread-row selected" : "forum-thread-row"
            }
          >
            <button
              type="button"
              onClick={() => onSelect(thread)}
              data-testid={`thread-${thread.id}`}
            >
              {thread.pinned && (
                <span className="forum-pinned-badge">
                  {t("forum.thread.pinned")}
                </span>
              )}{" "}
              {thread.title}
            </button>
          </li>
        ))}
      </ul>
      <div className="forum-pagination">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, safePage - 1))}
          disabled={safePage <= 1}
          data-testid="thread-prev"
        >
          {t("forum.pagination.prev")}
        </button>
        <span>
          {t("forum.pagination.label")} {safePage} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, safePage + 1))}
          disabled={safePage >= totalPages}
          data-testid="thread-next"
        >
          {t("forum.pagination.next")}
        </button>
      </div>
    </div>
  );
}
