import { es } from "../i18n/es";

/** Translate a flat key; falls back to the key itself when missing. */
export function t(key: string, vars?: Record<string, string | number>): string {
  const raw = es[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, k) =>
    k in vars ? String(vars[k]) : `{${k}}`,
  );
}

/** Hook form for components that want a stable t reference. */
export function useT(): {
  t: (key: string, vars?: Record<string, string | number>) => string;
} {
  return { t };
}