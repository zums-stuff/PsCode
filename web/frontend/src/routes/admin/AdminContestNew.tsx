import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { Contest } from "../../lib/types";

/** /admin/contests/new — create form (title, dates, scoring_mode, teams). */
export default function AdminContestNew() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [scoringMode, setScoringMode] = useState("cf");
  const [teamsEnabled, setTeamsEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toIso(local: string): string {
    if (!local) return "";
    return new Date(local).toISOString();
  }

  async function handleSave() {
    const startIso = toIso(startAt);
    const endIso = toIso(endAt);
    if (!startIso || !endIso) {
      setError(t("admin.contests.validation.future"));
      return;
    }
    if (new Date(endIso) <= new Date(startIso)) {
      setError(t("admin.contests.validation.endAfterStart"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await api.post<Contest>("/api/contests", {
        title: title.trim(),
        start_at: startIso,
        end_at: endIso,
        scoring_mode: scoringMode,
        teams_enabled: teamsEnabled,
      });
      navigate(`/admin/contests/${created.id}`);
    } catch {
      setError(t("admin.contests.createError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1>{t("admin.contests.newTitle")}</h1>

      <div className="form-field">
        <label htmlFor="contest-title">{t("admin.contests.fields.title")}</label>
        <input
          id="contest-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label htmlFor="contest-start">{t("admin.contests.fields.start_at")}</label>
        <input
          id="contest-start"
          type="datetime-local"
          value={startAt}
          onChange={(e) => setStartAt(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label htmlFor="contest-end">{t("admin.contests.fields.end_at")}</label>
        <input
          id="contest-end"
          type="datetime-local"
          value={endAt}
          onChange={(e) => setEndAt(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label htmlFor="contest-scoring">{t("admin.contests.fields.scoring_mode")}</label>
        <select
          id="contest-scoring"
          value={scoringMode}
          onChange={(e) => setScoringMode(e.target.value)}
        >
          <option value="cf">{t("admin.contests.scoring.cf")}</option>
          <option value="ioi">{t("admin.contests.scoring.ioi")}</option>
        </select>
      </div>

      <div className="form-field">
        <label>
          <input
            type="checkbox"
            checked={teamsEnabled}
            onChange={(e) => setTeamsEnabled(e.target.checked)}
          />{" "}
          {t("admin.contests.fields.teams_enabled")}
        </label>
      </div>

      {error && <p className="error">{error}</p>}

      <button
        type="button"
        className="primary"
        onClick={handleSave}
        disabled={saving || !title.trim()}
      >
        {saving ? t("admin.contests.creating") : t("admin.contests.create")}
      </button>
    </div>
  );
}
