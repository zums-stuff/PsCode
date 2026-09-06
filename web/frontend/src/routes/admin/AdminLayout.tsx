import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery, useQueries } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import type { AnticheatPair, ClassOut } from "../../lib/types";

const ANTICHEAT_THRESHOLD = 0.85;

/** Shared layout for /admin/* — header with nav, user badge, logout.
 *
 *  Sidebar nav: active route is highlighted via NavLink's `active` class;
 *  the anticheat link carries a badge with the global flagged-pair count
 *  (sum of `GET /api/admin/anticheat` over every visible class). */
export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const classesQuery = useQuery({
    queryKey: ["admin", "layout", "classes"],
    queryFn: () => api.get<ClassOut[]>("/api/classes"),
  });

  const anticheatQueries = useQueries({
    queries: (classesQuery.data ?? []).map((cls) => ({
      queryKey: ["admin", "dashboard", "anticheat", cls.id] as const,
      queryFn: () =>
        api.get<AnticheatPair[]>(
          `/api/admin/anticheat?scope=class&scope_id=${cls.id}&threshold=${ANTICHEAT_THRESHOLD}`,
        ),
      enabled: classesQuery.isSuccess,
    })),
  });

  const flaggedPairCount = anticheatQueries.reduce(
    (sum, q) => sum + (q.data?.length ?? 0),
    0,
  );

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  function navLinkClass(isActive: boolean): string {
    return isActive ? "admin-nav-link admin-nav-link-active" : "admin-nav-link";
  }

  return (
    <div className="admin-layout">
      <header className="admin-header">
        <span className="admin-brand">{t("app.title")}</span>
        <nav aria-label={t("admin.dashboard.nav.active")}>
          <NavLink
            to="/admin/problems"
            className={({ isActive }) => navLinkClass(isActive)}
          >
            {t("admin.problems.title")}
          </NavLink>
          <NavLink
            to="/admin/classes"
            className={({ isActive }) => navLinkClass(isActive)}
          >
            {t("admin.classes.title")}
          </NavLink>
          <NavLink
            to="/admin/contests"
            className={({ isActive }) => navLinkClass(isActive)}
          >
            {t("admin.contests.title")}
          </NavLink>
          <NavLink
            to="/admin/anticheat"
            className={({ isActive }) => navLinkClass(isActive)}
            data-testid="admin-nav-anticheat"
          >
            {t("admin.anticheat.title")}
            {flaggedPairCount > 0 && (
              <span
                className="admin-nav-badge"
                data-testid="admin-nav-anticheat-badge"
                data-count={flaggedPairCount}
              >
                {flaggedPairCount}
              </span>
            )}
          </NavLink>
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