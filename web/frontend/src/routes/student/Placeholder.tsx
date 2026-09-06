import { t } from "../../lib/i18n";

/**
 * Placeholder for student pages implemented in later todos (29-33).
 * Keeps the app shell routes real so guards/nav can be tested now.
 */
export default function Placeholder({ i18nKey }: { i18nKey: string }) {
  return (
    <div>
      <h1>{t(i18nKey)}</h1>
      <p>{t(`${i18nKey}.placeholder`)}</p>
    </div>
  );
}