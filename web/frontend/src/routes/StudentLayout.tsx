import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { t } from "../lib/i18n";
import ThemeToggle from "../components/ThemeToggle";

interface StudentNavItem {
  to: string;
  labelKey: string;
  exact?: boolean;
}

const PRIMARY_NAV: StudentNavItem[] = [
  { to: "/", labelKey: "student.nav.problems", exact: true },
  { to: "/practice", labelKey: "student.nav.practice" },
  { to: "/submissions", labelKey: "student.nav.submissions" },
  { to: "/forum", labelKey: "student.nav.forum" },
  { to: "/contests", labelKey: "student.nav.contests" },
];

function isNavItemActive(item: StudentNavItem, pathname: string): boolean {
  if (item.exact) return pathname === item.to;
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

/**
 * Shared layout for student routes (plan todo 27). Header with nav, user
 * badge, logout. Teachers/admins get a link back to /admin.
 *
 * Bug #2 fix: nav now uses NavLink + CSS flex row so the five primary links
 * sit horizontally with 1rem gap; the brand sits on the left, the user badge
 * + logout sit on the right (margin-left:auto). On narrow screens the row
 * wraps via flex-wrap.
 */
export default function StudentLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  function navClass(item: StudentNavItem): string {
    return isNavItemActive(item, location.pathname)
      ? "student-nav-link student-nav-link-active"
      : "student-nav-link";
  }

  return (
    <div className="student-layout">
      <header className="student-header">
        <span className="student-brand" data-testid="student-brand">
          {t("app.title")}
        </span>
        <div className="student-header-spacer" />
        <ThemeToggle compact />
        <nav>
          {PRIMARY_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={navClass(item)}
              data-testid={`student-nav-${item.to.replace(/^\//, "") || "home"}`}
            >
              {t(item.labelKey)}
            </NavLink>
          ))}
          {user?.role !== "student" && (
            <NavLink
              to="/admin/problems"
              className={({ isActive }) =>
                isActive
                  ? "student-nav-link student-nav-link-active"
                  : "student-nav-link"
              }
              data-testid="student-nav-admin"
            >
              {t("student.nav.admin")}
            </NavLink>
          )}
        </nav>
        <span className="student-user" data-testid="student-user">
          {user?.display_name} ({user?.role})
        </span>
        <button
          type="button"
          onClick={handleLogout}
          data-testid="student-logout"
        >
          {t("nav.logout")}
        </button>
      </header>
      <main className="student-content">
        <Outlet />
      </main>
    </div>
  );
}
