import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";

/**
 * Create-team modal for contest teams mode. POSTs a team name to
 * /api/contests/{id}/teams then invokes onCreated() on success.
 */
export default function CreateTeamModal({
  contestId,
  onClose,
  onCreated,
}: {
  contestId: number;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/api/contests/${contestId}/teams`, { name: name.trim() });
      onCreated();
    } catch {
      setError(t("admin.contests.teams.createError"));
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("admin.contests.teams.modal.title")}
      >
        <h2>{t("admin.contests.teams.modal.title")}</h2>
        {error && <p className="error">{error}</p>}
        <label htmlFor="create-team-name">{t("admin.contests.teams.name")}</label>
        <input
          id="create-team-name"
          type="text"
          data-testid="create-team-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
        />
        <div className="form-row">
          <button
            type="button"
            className="primary"
            onClick={() => void handleCreate()}
            disabled={!name.trim() || submitting}
            data-testid="create-team-submit"
          >
            {t("admin.contests.teams.modal.create")}
          </button>
          <button type="button" onClick={onClose} disabled={submitting}>
            {t("admin.contests.teams.modal.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}
