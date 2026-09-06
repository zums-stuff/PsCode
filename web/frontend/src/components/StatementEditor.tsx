import { useEffect, useRef, useState, type ReactNode } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { pseint } from "@codemirror/lang-pseint";
import { t } from "../lib/i18n";

interface StatementEditorProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Markdown statement editor: textarea + preview tab. Fenced code blocks in
 * the preview render through a read-only CodeMirror view with the pseint
 * mode (todo 28). Markdown rendering is a hand-rolled minimal subset
 * (headings, paragraphs, bold/italic, inline code, code fences).
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
        <div className="markdown-preview">{renderMarkdown(value)}</div>
      )}
    </div>
  );
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inlineMarkdown(text: string): ReactNode[] {
  const escaped = escapeHtml(text);
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(escaped)) !== null) {
    if (match.index > last) nodes.push(escaped.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={key++}>{token.slice(1, -1)}</code>);
    } else {
      nodes.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < escaped.length) nodes.push(escaped.slice(last));
  return nodes;
}

/** Markdown -> React nodes (headings, paragraphs, bold/italic, inline code, fences). */
export function renderMarkdown(markdown: string): ReactNode {
  const lines = markdown.split("\n");
  const nodes: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const trimmed = lines[i].trim();

    if (trimmed.startsWith("```")) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        code.push(lines[i]);
        i += 1;
      }
      i += 1; // skip closing fence (or end of input)
      nodes.push(<PseintCodeBlock key={key++} code={code.join("\n")} />);
      continue;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const Tag = (level === 1 ? "h1" : level === 2 ? "h2" : "h3") as
        | "h1"
        | "h2"
        | "h3";
      nodes.push(<Tag key={key++}>{inlineMarkdown(heading[2])}</Tag>);
      i += 1;
      continue;
    }

    if (trimmed === "") {
      i += 1;
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].trim().startsWith("```") &&
      !/^#{1,3}\s/.test(lines[i].trim())
    ) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    nodes.push(<p key={key++}>{inlineMarkdown(paragraph.join(" "))}</p>);
  }

  return <>{nodes}</>;
}

/** Read-only CodeMirror view with the pseint mode for a fenced code block. */
function PseintCodeBlock({ code }: { code: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: code,
        extensions: [
          pseint(),
          EditorView.editable.of(false),
          EditorView.lineWrapping,
        ],
      }),
      parent: container,
    });
    return () => view.destroy();
  }, [code]);

  return <div ref={containerRef} className="code-block" />;
}