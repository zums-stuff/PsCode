import { useState } from "react";
import { t } from "../lib/i18n";
import Markdown from "./Markdown";

interface StatementEditorProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Markdown statement editor: textarea + preview tab. Fenced code blocks in
 * the preview render through a read-only CodeMirror view with the pseint
 * mode (todo 28). Markdown rendering delegates to `<Markdown>` which uses
 * `react-markdown` + `remark-math` + `rehype-katex` (KaTeX) so the
 * preview matches the read-only solve-page pane (todo 22 + bug 3 fix).
 */
export default function StatementEditor({ value, onChange }: StatementEditorProps) {
  const [tab, setTab] = useState<"edit" | "preview">("edit");

  return (
    <div className="statement-editor">
      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "edit"}
          onClick={() => setTab("edit")}
        >
          {t("statementEditor.edit")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "preview"}
          onClick={() => setTab("preview")}
        >
          {t("statementEditor.preview")}
        </button>
      </div>
      {tab === "edit" ? (
        <textarea
          aria-label={t("admin.problem.fields.statement")}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={t("statementEditor.placeholder")}
          rows={12}
        />
      ) : (
        <div className="markdown-preview">
          <Markdown source={value} />
        </div>
      )}
    </div>
  );
}