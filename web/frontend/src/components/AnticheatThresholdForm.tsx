import { useState } from "react";
import { t } from "../lib/i18n";

interface AnticheatThresholdFormProps {
  classId: number;
  /** Current persisted value (from the class detail / list). */
  initialThreshold: number;
  /** Default value shown as a hint when the input is empty. */
  defaultThreshold: number;
  /** Fired with a validated threshold in [0, 1]. */
  onSubmit: (threshold: number) => Promise<void> | void;
  /** Disable the form (e.g. while submitting). */
  disabled?: boolean;
}

/**
 * /admin/anticheat threshold input (todo 25 / todo 39).
 *
 * The input value is validated client-side to [0, 1] (the same constraint
 * the Pydantic ``Field(ge=0.0, le=1.0)`` enforces server-side).  On submit
 * the parent calls ``POST /api/admin/classes/{id}/anticheat-threshold``.
 */
export default function AnticheatThresholdForm({
  classId,
  initialThreshold,
  defaultThreshold,
  onSubmit,
  disabled,
}: AnticheatThresholdFormProps) {
  const [valueText, setValueText] = useState<string>(
    String(initialThreshold),
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<boolean>(false);

  function validate(text: string): number | null {
    const parsed = Number.parseFloat(text);
    if (!Number.isFinite(parsed)) return null;
    if (parsed < 0 || parsed > 1) return null;
    return parsed;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = validate(valueText);
    if (parsed === null) {
      setError(t("admin.anticheat.threshold.invalid"));
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await onSubmit(parsed);
    } catch {
      setError(t("admin.anticheat.threshold.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="anticheat-threshold-form" onSubmit={handleSubmit} noValidate>
      <div className="form-field">
        <label htmlFor={`anticheat-threshold-${classId}`}>
          {t("admin.anticheat.threshold.label")}
        </label>
        <input
          id={`anticheat-threshold-${classId}`}
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={valueText}
          onChange={(e) => setValueText(e.target.value)}
          disabled={disabled === true || saving}
          placeholder={String(defaultThreshold)}
        />
        <span className="hint">{t("admin.anticheat.threshold.hint")}</span>
      </div>
      <div className="form-field">
        <button
          type="submit"
          className="primary"
          disabled={disabled === true || saving}
        >
          {saving
            ? t("admin.anticheat.threshold.saving")
            : t("admin.anticheat.threshold.save")}
        </button>
      </div>
      {error !== null && <p className="error">{error}</p>}
    </form>
  );
}
