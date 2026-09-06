import { Link } from "react-router-dom";
import { t } from "../lib/i18n";

export default function NotFound() {
  return (
    <div className="auth-page">
      <h1>{t("notFound.title")}</h1>
      <p>{t("notFound.message")}</p>
      <Link to="/">{t("app.title")}</Link>
    </div>
  );
}