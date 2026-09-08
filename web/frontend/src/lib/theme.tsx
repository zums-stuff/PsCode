/**
 * Theme provider (UX P0 — dark mode + system-aware).
 *
 * Resolves the theme in this order:
 *   1. Manual override stored in localStorage ("light" | "dark" | "system")
 *   2. If "system" (default), `prefers-color-scheme: dark` media query
 *   3. Otherwise light
 *
 * The resolved value is set as ``<html data-theme="light|dark">`` so CSS
 * variables override cleanly without runtime JS style mutations.
 *
 * Usage:
 *   <ThemeProvider>...</ThemeProvider>  (wrap near root, after auth)
 *   const { theme, setTheme, resolved } = useTheme()
 *   setTheme("dark") | "light" | "system"
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "pseint:theme";

function readInitialPreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // localStorage blocked — fall through to "system"
  }
  return "system";
}

function resolveSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

interface ThemeContextValue {
  /** User's choice (may be "system"). */
  theme: ThemePreference;
  /** The actual theme applied to the DOM ("light" | "dark"). */
  resolved: ResolvedTheme;
  /** Update the user's preference; persists to localStorage. */
  setTheme: (next: ThemePreference) => void;
  /** True iff the resolved theme is dark. Convenience for components. */
  isDark: boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(readInitialPreference);
  const [resolved, setResolved] = useState<ResolvedTheme>(resolveSystemTheme);

  // Track system preference changes when the user has chosen "system".
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (theme === "system") setResolved(mq.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  // Resolve the active theme whenever the preference changes.
  useEffect(() => {
    if (theme === "system") setResolved(resolveSystemTheme());
    else setResolved(theme);
  }, [theme]);

  // Apply to the <html> element so CSS variables cascade through the tree.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-theme", resolved);
  }, [resolved]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolved, setTheme, isDark: resolved === "dark" }),
    [theme, resolved, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (ctx !== null) return ctx;
  // Graceful fallback (tests, isolated renders): return a sensible default
  // rather than crashing. The DOM attribute will not be set in this case,
  // so the CSS uses the :root defaults.
  return {
    theme: "system",
    resolved: "light",
    setTheme: () => {},
    isDark: false,
  };
}
