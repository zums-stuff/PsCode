import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import type { ClassOut, ContestParticipant } from "../lib/types";
import PhaseAwareActions from "./PhaseAwareActions";

/**
 * Contest participants panel: list current participants, add a whole class
 * (bulk) or an individual user. Add actions are disabled before the contest
 * starts (PhaseAwareActions).
 */
export default function ParticipantsPanel({
  contestId,
  phase,
  participants,
  onChanged,
}: {
  contestId: number;
  phase: string;
  participants: ContestParticipant[];
  onChanged: () => void;
}) {
  const [classId, setClassId] = useState("");
  const [userId, setUserId] = useState("");
  const [classes, setClasses] = useState<ClassOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function loadClasses() {
    try {
      setClasses(await api.get<ClassOut[]>("/api/classes"));
    } catch {
      setClasses([]);
    }
  }

  async function handleAddClass() {
    if (!classId) return;
    setError(null);
    try {
      await api.post(`/api/contests/${contestId}/participants/class/${classId}`);
      setClassId("");
      onChanged();
    } catch {
      setError(t("admin.contests.participants.addError"));
    }
  }

  async function handleAddUser() {
    if (!userId) return;
    setError(null);
    try {
      await api.post(`/api/contests/${contestId}/participants/user/${Number(userId)}`);
      setUserId("");
      onChanged();
    } catch {
      setError(t("admin.contests.participants.addError"));
    }
  }

  return (
    <div>
      {participants.length === 0 && <p>{t("admin.contests.participants.empty")}</p>}
      {participants.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("admin.contests.participants.username")}</th>
            </tr>
          </thead>
          <tbody>
            {participants.map((p) => (
              <tr key={p.user_id}>
                <td>{p.username}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {error && <p className="error">{error}</p>}
      <div className="form-row">
        <select
          value={classId}
          onChange={(e) => setClassId(e.target.value)}
          onFocus={loadClasses}
        >
          <option value="">{t("admin.contests.participants.selectClass")}</option>
          {classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <PhaseAwareActions phase={phase}>
          <button
            type="button"
            onClick={handleAddClass}
            disabled={!classId}
          >
            {t("admin.contests.participants.add_class")}
          </button>
        </PhaseAwareActions>
      </div>
      <div className="form-row">
        <input
          type="number"
          placeholder={t("admin.contests.participants.userId")}
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
        />
        <PhaseAwareActions phase={phase}>
          <button
            type="button"
            onClick={handleAddUser}
            disabled={!userId}
          >
            {t("admin.contests.participants.add_individual")}
          </button>
        </PhaseAwareActions>
      </div>
    </div>
  );
}
