import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { t } from "../lib/i18n";

/**
 * Shared layout for student routes (plan todo 27). Header with nav, user
 * badge, logout. Teachers/admins get a link back to /admin.
 */
export default function StudentLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="student-layout">
      <header className="student-header">
        <span className="student-brand">{t("app.title")}</span>
        <nav>
          <Link to="/">{t("student.nav.problems")}</Link>
          <Link to="/practice">{t("student.nav.practice")}</Link>
          <Link to="/submissions">{t("student.nav.submissions")}</Link>
          <Link to="/forum">{t("student.nav.forum")}</Link>
          <Link to="/contests">{t("student.nav.contests")}</Link>
          {user?.role !== "student" && (
            <Link to="/admin/problems">{t("student.nav.admin")}</Link>
          )}
        </nav>
        <span className="student-user">
          {user?.display_name} ({user?.role})
        </span>
        <button type="button" onClick={handleLogout}>
          {t("nav.logout")}
        </button>
      </header>
      <main className="student-content">
        <Outlet />
      </main>
    </div>
  );
}