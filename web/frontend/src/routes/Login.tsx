import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { t } from "../lib/i18n";

/**
 * Minimal functional login (todo 27 builds the full auth pages; this one
 * hits POST /api/login + GET /api/me so the admin flow is usable now).
 */
export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: { pathname?: string } } | null)?.from
    ?.pathname;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const me = await login(username, password);
      navigate(from ?? (me.role === "student" ? "/" : "/admin/problems"), {
        replace: true,
      });
    } catch {
      setError(t("login.error"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>{t("login.title")}</h1>
      <form onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="login-username">{t("login.username")}</label>
          <input
            id="login-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </div>
        <div className="form-field">
          <label htmlFor="login-password">{t("login.password")}</label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        {error && <p className="error">{error}</p>}
        <button type="submit" className="primary" disabled={submitting}>
          {t("login.submit")}
        </button>
      </form>
      <p>
        <Link to="/register">{t("login.registerHint")}</Link>
      </p>
    </div>
  );
}