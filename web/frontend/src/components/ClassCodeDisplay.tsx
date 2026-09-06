import { useState } from "react";
import { t } from "../lib/i18n";

/** 6-char class join code with a copy-to-clipboard button. */
export default function ClassCodeDisplay({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <span className="class-code">
      <code>{code}</code>
      <button type="button" onClick={handleCopy}>
        {copied ? t("admin.classes.code.copied") : t("admin.classes.code.copy")}
      </button>
    </span>
  );
}