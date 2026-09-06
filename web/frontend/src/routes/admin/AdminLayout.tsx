import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";

/** Shared layout for /admin/* — header with nav, user badge, logout. */
export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="admin-layout">
      <header className="admin-header">
        <span className="admin-brand">{t("app.title")}</span>
        <nav>
          <Link to="/admin/problems">{t("admin.problems.title")}</Link>
          <Link to="/admin/classes">{t("admin.classes.title")}</Link>
          <Link to="/admin/contests">{t("admin.contests.title")}</Link>
          <Link to="/admin/anticheat">{t("admin.anticheat.title")}</Link>
        </nav>
        <span className="admin-user">
          {user?.display_name} ({user?.role})
        </span>
        <button type="button" onClick={handleLogout}>
          {t("nav.logout")}
        </button>
      </header>
      <main className="admin-content">
        <Outlet />
      </main>
    </div>
  );
}