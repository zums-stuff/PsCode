import { useTheme, type ThemePreference } from "../lib/theme";
import { t } from "../lib/i18n";

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme, resolved } = useTheme();

  const options: { value: ThemePreference; labelKey: string; icon: string }[] = [
    { value: "light", labelKey: "nav.theme.light", icon: "☀" },
    { value: "dark", labelKey: "nav.theme.dark", icon: "☾" },
    { value: "system", labelKey: "nav.theme.system", icon: "◐" },
  ];

  return (
    <div
      className={`theme-toggle ${compact ? "theme-toggle-compact" : ""}`}
      role="radiogroup"
      aria-label={t("nav.theme.label")}
      data-active={resolved}
    >
      {options.map((opt) => {
        const label = t(opt.labelKey);
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={theme === opt.value}
            className="theme-toggle-btn"
            onClick={() => setTheme(opt.value)}
            title={`${label}${theme === opt.value ? " (actual)" : ""}`}
          >
            <span aria-hidden="true" className="theme-toggle-icon">
              {opt.icon}
            </span>
            {!compact && <span className="theme-toggle-label">{label}</span>}
          </button>
        );
      })}
    </div>
  );
}
