import { Link } from "react-router-dom";
import { t } from "../lib/i18n";

export default function Forbidden() {
  return (
    <div className="auth-page">
      <h1>{t("forbidden.title")}</h1>
      <p>{t("forbidden.message")}</p>
      <Link to="/login">{t("login.title")}</Link>
    </div>
  );
}