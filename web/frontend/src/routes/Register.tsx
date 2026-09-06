import { Link } from "react-router-dom";
import { t } from "../lib/i18n";

/** Placeholder — todo 27 builds the real student registration page. */
export default function Register() {
  return (
    <div className="auth-page">
      <h1>{t("register.title")}</h1>
      <p>{t("register.soon")}</p>
      <Link to="/login">{t("login.title")}</Link>
    </div>
  );
}