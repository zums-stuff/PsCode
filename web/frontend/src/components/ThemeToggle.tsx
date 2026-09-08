import { useTheme, type ThemePreference } from "../lib/theme";

/**
 * Theme toggle (UX P0 — dark mode).
 *
 * Three-state segmented control: Light / Dark / System. Persists via
 * ThemeProvider; visually shows the active state with the accent border.
 *
 * Renders inline (suitable for header bars). Touch-friendly: 36px+ tap
 * targets; clear focus ring via :focus-visible.
 */
export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme, resolved } = useTheme();

  const options: { value: ThemePreference; label: string; icon: string }[] = [
    { value: "light", label: "Claro", icon: "☀" },
    { value: "dark", label: "Oscuro", icon: "☾" },
    { value: "system", label: "Sistema", icon: "◐" },
  ];

  return (
    <div
      className={`theme-toggle ${compact ? "theme-toggle-compact" : ""}`}
      role="radiogroup"
      aria-label="Tema visual"
      data-active={resolved}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={theme === opt.value}
          className="theme-toggle-btn"
          onClick={() => setTheme(opt.value)}
          title={`${opt.label}${theme === opt.value ? " (actual)" : ""}`}
        >
          <span aria-hidden="true" className="theme-toggle-icon">
            {opt.icon}
          </span>
          {!compact && <span className="theme-toggle-label">{opt.label}</span>}
        </button>
      ))}
    </div>
  );
}
