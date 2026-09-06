import { es } from "../i18n/es";

/** Translate a flat key; falls back to the key itself when missing. */
export function t(key: string): string {
  return es[key] ?? key;
}

/** Hook form for components that want a stable t reference. */
export function useT(): { t: (key: string) => string } {
  return { t };
}