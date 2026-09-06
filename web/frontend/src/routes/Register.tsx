import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { t } from "../lib/i18n";
import type { AuthUser } from "../lib/types";

/**
 * Student registration (plan todo 27). POST /api/register with
 * username/display_name/password/class_code (optional), then auto-login via
 * the auth context so the student lands on /problems.
 */
export default function Register() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [classCode, setClassCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!username.trim()) {
      setError(t("register.validation.username"));
      return;
    }
    if (!displayName.trim()) {
      setError(t("register.validation.displayName"));
      return;
    }
    if (password.length < 8) {
      setError(t("register.validation.password"));
      return;
    }

    setSubmitting(true);
    try {
      await api.post<AuthUser>("/api/register", {
        username: username.trim(),
        display_name: displayName.trim(),
        password,
        class_code: classCode.trim() || null,
      });
      // Auto-login so the student lands on /problems.
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch {
      setError(t("register.error"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>{t("register.title")}</h1>
      <form onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="register-username">{t("register.username")}</label>
          <input
            id="register-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </div>
        <div className="form-field">
          <label htmlFor="register-display">{t("register.displayName")}</label>
          <input
            id="register-display"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            autoComplete="name"
          />
        </div>
        <div className="form-field">
          <label htmlFor="register-password">{t("register.password")}</label>
          <input
            id="register-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div className="form-field">
          <label htmlFor="register-class">{t("register.classCode")}</label>
          <input
            id="register-class"
            type="text"
            value={classCode}
            onChange={(e) => setClassCode(e.target.value)}
            autoComplete="off"
          />
        </div>
        {error && <p className="error">{error}</p>}
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? t("register.submitting") : t("register.submit")}
        </button>
      </form>
      <p>
        <Link to="/login">{t("register.loginHint")}</Link>
      </p>
    </div>
  );
}
