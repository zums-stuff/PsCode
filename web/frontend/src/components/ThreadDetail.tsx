import { useMemo, useState } from "react";
import type * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  deleteForumPost,
  listForumPosts,
  pinForumThread,
  updateForumPost,
} from "../lib/api";
import { t } from "../lib/i18n";
import type { AuthUser, ForumPost } from "../lib/types";

interface ThreadDetailProps {
  threadId: number;
  threadPinned: boolean;
  user: AuthUser | null;
  onBack: () => void;
}

const CONTEST_LOCK_DETAIL = "Contest in progress: only teachers can post";

/**
 * Thread detail view (todo 33). Loads posts, renders top-level posts and
 * nested replies (parent_id), exposes a reply box that surfaces the
 * contest-phase 403 as a friendly toast. Teachers/admins see pin/edit/delete
 * controls — every action calls the moderation endpoint and invalidates the
 * matching query so the list refetches.
 */
export default function ThreadDetail({
  threadId,
  threadPinned,
  user,
  onBack,
}: ThreadDetailProps) {
  const queryClient = useQueryClient();
  const isModerator = user?.role === "teacher" || user?.role === "admin";

  const postsQuery = useQuery({
    queryKey: ["forum", "posts", threadId],
    queryFn: () => listForumPosts(threadId),
  });

  const [replyTo, setReplyTo] = useState<number | null>(null);
  const [replyBody, setReplyBody] = useState("");
  const [replyError, setReplyError] = useState<string | null>(null);
  const [replying, setReplying] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingBody, setEditingBody] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  const replyMutation = useMutation({
    mutationFn: async ({
      body,
      parentId,
    }: {
      body: string;
      parentId: number | null;
    }) => {
      const { createForumPost } = await import("../lib/api");
      return createForumPost(threadId, body, parentId ?? undefined);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["forum", "posts", threadId] });
      setReplyBody("");
      setReplyTo(null);
      setReplyError(null);
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.status === 403) {
        setReplyError(t("forum.thread.contestLock"));
        setToast(t("forum.thread.contestLockToast"));
      } else {
        setReplyError(t("forum.thread.postError"));
      }
    },
    onSettled: () => setReplying(false),
  });

  const pinMutation = useMutation({
    mutationFn: (pinned: boolean) => pinForumThread(threadId, pinned),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["forum", "threads"],
      });
    },
  });

  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: string }) =>
      updateForumPost(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["forum", "posts", threadId] });
      setEditingId(null);
      setEditingBody("");
      setEditError(null);
    },
    onError: () => setEditError(t("forum.thread.editError")),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteForumPost(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["forum", "posts", threadId] });
    },
  });

  const grouped = useMemo(() => {
    const posts = postsQuery.data ?? [];
    const ids = new Set(posts.map((p) => p.id));
    const top: ForumPost[] = [];
    const children = new Map<number, ForumPost[]>();
    for (const p of posts) {
      if (p.parent_id !== null && ids.has(p.parent_id)) {
        const list = children.get(p.parent_id) ?? [];
        list.push(p);
        children.set(p.parent_id, list);
      } else {
        // parent_id is null or refers to a post outside this thread (orphan).
        top.push(p);
      }
    }
    return { top, children };
  }, [postsQuery.data]);

  if (postsQuery.isLoading) {
    return <p>{t("forum.loading")}</p>;
  }
  if (postsQuery.isError) {
    return <p className="error">{t("forum.loadError")}</p>;
  }

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (replyBody.trim().length === 0) return;
    setReplying(true);
    setReplyError(null);
    replyMutation.mutate({ body: replyBody, parentId: replyTo });
  }

  function startEdit(post: ForumPost) {
    setEditingId(post.id);
    setEditingBody(post.body);
    setEditError(null);
  }

  function saveEdit(id: number) {
    if (editingBody.trim().length === 0) return;
    editMutation.mutate({ id, body: editingBody });
  }

  return (
    <div className="forum-thread-detail" data-testid="thread-detail">
      <div className="forum-thread-detail-header">
        <button type="button" onClick={onBack} data-testid="thread-back">
          {t("forum.thread.back")}
        </button>
        {isModerator && (
          <button
            type="button"
            onClick={() => pinMutation.mutate(!threadPinned)}
            data-testid="thread-pin"
          >
            {threadPinned ? t("forum.thread.unpin") : t("forum.thread.pin")}
          </button>
        )}
      </div>

      {toast !== null && (
        <p className="error" data-testid="forum-toast" role="alert">
          {toast}
        </p>
      )}

      <ul className="forum-posts">
        {grouped.top.map((post) => (
          <li key={post.id} className="forum-post" data-testid={`post-${post.id}`}>
            <PostNode
              post={post}
              depth={0}
              tree={grouped.children}
              isModerator={isModerator}
              editingId={editingId}
              editingBody={editingBody}
              replyTo={replyTo}
              replyBody={replyBody}
              replyError={replyError}
              replying={replying}
              onEditStart={startEdit}
              onEditChange={setEditingBody}
              onEditSave={saveEdit}
              onEditCancel={() => { setEditingId(null); setEditingBody(""); }}
              onDelete={(id) => {
                if (window.confirm(t("forum.thread.deleteConfirm"))) {
                  deleteMutation.mutate(id);
                }
              }}
              onReplyStart={(id) => { setReplyTo(id); setReplyBody(""); setReplyError(null); }}
              onReplyChange={setReplyBody}
              onReplyCancel={() => { setReplyTo(null); setReplyError(null); }}
              onReplySubmit={handleReply}
            />
          </li>
        ))}
      </ul>

      {editError !== null && (
        <p className="error" data-testid="edit-error">
          {editError}
        </p>
      )}

      {replyTo === null && (
        <form
          className="forum-reply-form"
          onSubmit={handleReply}
          data-testid="top-reply-form"
        >
          <div className="form-field">
            <label htmlFor="top-reply-body">{t("forum.thread.reply")}</label>
            <textarea
              id="top-reply-body"
              value={replyBody}
              onChange={(e) => setReplyBody(e.target.value)}
              placeholder={t("forum.thread.replyPlaceholder")}
              rows={3}
            />
          </div>
          {replyError !== null && (
            <p className="error" data-testid="reply-error">
              {replyError}
            </p>
          )}
          <button
            type="submit"
            className="primary"
            disabled={replying || replyBody.trim().length === 0}
            data-testid="top-reply-submit"
          >
            {replying
              ? t("forum.thread.submittingReply")
              : t("forum.thread.submitReply")}
          </button>
        </form>
      )}
    </div>
  );
}

interface PostNodeProps {
  post: ForumPost;
  depth: number;
  tree: Map<number, ForumPost[]>;
  isModerator: boolean;
  editingId: number | null;
  editingBody: string;
  replyTo: number | null;
  replyBody: string;
  replyError: string | null;
  replying: boolean;
  onEditStart: (post: ForumPost) => void;
  onEditChange: (body: string) => void;
  onEditSave: (id: number) => void;
  onEditCancel: () => void;
  onDelete: (id: number) => void;
  onReplyStart: (id: number) => void;
  onReplyChange: (body: string) => void;
  onReplyCancel: () => void;
  onReplySubmit: (e: React.FormEvent) => void;
}

const MAX_INLINE = 3;
const MAX_DEPTH = 5;

function PostNode({
  post,
  depth,
  tree,
  isModerator,
  editingId,
  editingBody,
  replyTo,
  replyBody,
  replyError,
  replying,
  onEditStart,
  onEditChange,
  onEditSave,
  onEditCancel,
  onDelete,
  onReplyStart,
  onReplyChange,
  onReplyCancel,
  onReplySubmit,
}: PostNodeProps) {
  const [showAll, setShowAll] = useState(false);
  const children = tree.get(post.id) ?? [];
  const visibleChildren = showAll ? children : children.slice(0, MAX_INLINE);

  return (
    <article
      className="post-node"
      data-depth={depth}
      data-testid={`postnode-${post.id}`}
    >
      <PostBody
        post={post}
        isModerator={isModerator}
        editing={editingId === post.id}
        editingBody={editingBody}
        onEditStart={onEditStart}
        onEditChange={onEditChange}
        onEditSave={onEditSave}
        onEditCancel={onEditCancel}
        onDelete={onDelete}
      />
      <button
        type="button"
        onClick={() => onReplyStart(post.id)}
        data-testid={`reply-to-${post.id}`}
      >
        {t("forum.thread.reply")}
      </button>
      {replyTo === post.id && (
        <ReplyForm
          parentId={post.id}
          body={replyBody}
          error={replyError}
          submitting={replying}
          onChange={onReplyChange}
          onCancel={onReplyCancel}
          onSubmit={onReplySubmit}
        />
      )}
      {children.length > MAX_INLINE && !showAll && (
        <button
          type="button"
          className="show-more"
          onClick={() => setShowAll(true)}
          data-testid={`show-more-${post.id}`}
        >
          + {children.length - MAX_INLINE} {t("forum.thread.showMore")}
        </button>
      )}
      {visibleChildren.length > 0 && (
        <div className="post-children" data-testid={`children-${post.id}`}>
          {visibleChildren.map((child) => (
            <PostNode
              key={child.id}
              post={child}
              depth={Math.min(depth + 1, MAX_DEPTH)}
              tree={tree}
              isModerator={isModerator}
              editingId={editingId}
              editingBody={editingBody}
              replyTo={replyTo}
              replyBody={replyBody}
              replyError={replyError}
              replying={replying}
              onEditStart={onEditStart}
              onEditChange={onEditChange}
              onEditSave={onEditSave}
              onEditCancel={onEditCancel}
              onDelete={onDelete}
              onReplyStart={onReplyStart}
              onReplyChange={onReplyChange}
              onReplyCancel={onReplyCancel}
              onReplySubmit={onReplySubmit}
            />
          ))}
        </div>
      )}
    </article>
  );
}

/**
 * Render a post body, turning fenced ```pseint code blocks into <pre> with
 * monospaced formatting while keeping the rest as paragraph lines.  No
 * markdown dependency — just the code-block case that matters for snippets.
 */
function renderPostBody(body: string) {
  const parts: React.ReactNode[] = [];
  const blocks = body.split(/```/);
  blocks.forEach((seg, i) => {
    // Even segments are prose; odd segments are fenced code.
    if (i % 2 === 1) {
      const code = seg.replace(/^pseint\s*\n/i, "");
      parts.push(
        <pre key={i} className="forum-code-block">
          <code>{code}</code>
        </pre>,
      );
    } else if (seg.trim().length > 0) {
      parts.push(
        <p key={i} className="forum-post-paragraph">
          {seg}
        </p>,
      );
    }
  });
  return parts;
}

interface PostBodyProps {  post: ForumPost;
  isModerator: boolean;
  editing: boolean;
  editingBody: string;
  onEditStart: (post: ForumPost) => void;
  onEditChange: (body: string) => void;
  onEditSave: (id: number) => void;
  onEditCancel: () => void;
  onDelete: (id: number) => void;
}

function PostBody({
  post,
  isModerator,
  editing,
  editingBody,
  onEditStart,
  onEditChange,
  onEditSave,
  onEditCancel,
  onDelete,
}: PostBodyProps) {
  if (editing) {
    return (
      <div className="forum-post-edit" data-testid={`edit-${post.id}`}>
        <textarea
          value={editingBody}
          onChange={(e) => onEditChange(e.target.value)}
          rows={3}
          data-testid={`edit-body-${post.id}`}
        />
        <div className="form-row">
          <button
            type="button"
            className="primary"
            onClick={() => onEditSave(post.id)}
            data-testid={`edit-save-${post.id}`}
          >
            {t("forum.thread.saveEdit")}
          </button>
          <button type="button" onClick={onEditCancel}>
            {t("forum.thread.cancelEdit")}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="forum-post-body">
      {renderPostBody(post.body)}
      <small>
        #{post.id} · {post.created_at}
      </small>
      {isModerator && (
        <div className="forum-post-moderate">
          <button
            type="button"
            onClick={() => onEditStart(post)}
            data-testid={`edit-button-${post.id}`}
          >
            {t("forum.thread.edit")}
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => onDelete(post.id)}
            data-testid={`delete-button-${post.id}`}
          >
            {t("forum.thread.delete")}
          </button>
        </div>
      )}
    </div>
  );
}

interface ReplyFormProps {
  parentId: number;
  body: string;
  error: string | null;
  submitting: boolean;
  onChange: (v: string) => void;
  onCancel: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

function ReplyForm({
  parentId,
  body,
  error,
  submitting,
  onChange,
  onCancel,
  onSubmit,
}: ReplyFormProps) {
  return (
    <form
      className="forum-reply-form"
      onSubmit={onSubmit}
      data-testid={`reply-form-${parentId}`}
    >
      <div className="form-field">
        <label htmlFor={`reply-body-${parentId}`}>
          {t("forum.post.replyTo")} #{parentId}
        </label>
        <textarea
          id={`reply-body-${parentId}`}
          value={body}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
        />
      </div>
      {error !== null && (
        <p className="error" data-testid={`reply-error-${parentId}`}>
          {error}
        </p>
      )}
      <div className="form-row">
        <button
          type="submit"
          className="primary"
          disabled={submitting || body.trim().length === 0}
          data-testid={`reply-submit-${parentId}`}
        >
          {submitting
            ? t("forum.thread.submittingReply")
            : t("forum.thread.submitReply")}
        </button>
        <button type="button" onClick={onCancel}>
          {t("forum.post.cancelReply")}
        </button>
      </div>
    </form>
  );
}
