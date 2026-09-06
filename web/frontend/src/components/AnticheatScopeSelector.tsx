import { useState } from "react";
import { t } from "../lib/i18n";

export type AnticheatScope = "class" | "contest";

export interface ScopeSelection {
  scope: AnticheatScope;
  scopeId: number;
}

interface AnticheatScopeSelectorProps {
  /** Currently-selected scope/scope_id (controlled). */
  value: ScopeSelection | null;
  /** Fired when the user confirms a new selection. */
  onApply: (selection: ScopeSelection) => void;
}

/**
 * /admin/anticheat scope picker (todo 25).
 *
 * Two controls — scope kind (class / contest) and the numeric scope id —
 * plus an "Aplicar" button.  The picker is intentionally a *form*: the list
 * is not refetched until the teacher confirms, so accidental id edits don't
 * fire network calls.
 */
export default function AnticheatScopeSelector({
  value,
  onApply,
}: AnticheatScopeSelectorProps) {
  const [scope, setScope] = useState<AnticheatScope>(
    value?.scope ?? "class",
  );
  const [scopeIdText, setScopeIdText] = useState<string>(
    value?.scopeId !== undefined ? String(value.scopeId) : "",
  );
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const scopeId = Number.parseInt(scopeIdText, 10);
    if (!Number.isInteger(scopeId) || scopeId < 1) {
      setError(t("admin.anticheat.scope.invalidId"));
      return;
    }
    setError(null);
    onApply({ scope, scopeId });
  }

  return (
    <form className="anticheat-scope-selector" onSubmit={handleSubmit} noValidate>
      <div className="form-field">
        <label htmlFor="anticheat-scope-kind">
          {t("admin.anticheat.scope.kind")}
        </label>
        <select
          id="anticheat-scope-kind"
          value={scope}
          onChange={(e) => setScope(e.target.value as AnticheatScope)}
        >
          <option value="class">{t("admin.anticheat.scope.class")}</option>
          <option value="contest">{t("admin.anticheat.scope.contest")}</option>
        </select>
      </div>
      <div className="form-field">
        <label htmlFor="anticheat-scope-id">
          {t("admin.anticheat.scope.id")}
        </label>
        <input
          id="anticheat-scope-id"
          type="number"
          min={1}
          step={1}
          value={scopeIdText}
          onChange={(e) => setScopeIdText(e.target.value)}
          required
        />
      </div>
      <div className="form-field">
        <button type="submit" className="primary">
          {t("admin.anticheat.scope.apply")}
        </button>
      </div>
      {error !== null && <p className="error">{error}</p>}
    </form>
  );
}
