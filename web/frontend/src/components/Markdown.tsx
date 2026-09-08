import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { pseint } from "@codemirror/lang-pseint";

interface MarkdownProps {
  source: string;
}

/**
 * HTML entity decoder for math nodes (bug 3 fix).
 *
 * CommonMark decodes entities at parse time for prose text, but the math
 * node content is passed verbatim to KaTeX, which doesn't understand
 * entities — `$n &gt;= 0$` produces a KaTeX parse error instead of the
 * intended `n >= 0`.  We pre-decode a small set of named / numeric
 * entities at the source-string level so math sees plain text and KaTeX
 * renders correctly.
 *
 * `&amp;` is intentionally NOT decoded here — CommonMark handles it for
 * prose text and would double-decode `&amp;gt;` → `&gt;` → `>`.  We
 * only decode the entities KaTeX chokes on.
 *
 * The regex only matches COMPLETE entities (named or numeric), so an
 * accidental `&xyz;` round-trips untouched.
 */
function decodeEntities(s: string): string {
  return s.replace(
    /&(?:lt|gt|quot|apos|#39);/g,
    (m) =>
      ({
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&apos;": "'",
        "&#39;": "'",
      })[m] ?? m,
  );
}

/**
 * Read-only CodeMirror view with the pseint mode, used inside markdown
 * fenced code blocks (todo 22). Same widget as StatementEditor's
 * previous preview; extracted so the new <Markdown> wrapper can drop it
 * into a react-markdown `code` override.
 */
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

/**
 * Markdown renderer for problem statements (todo 22 + bug 3 fix).
 *
 * Replaces the hand-rolled subset (headings / paragraphs / bold / italic /
 * inline code / fences) in `StatementEditor.tsx`'s `renderMarkdown`. Adds
 * LaTeX-style math (`$inline$` and `$$block$$`) via `remark-math` +
 * `rehype-katex` (KaTeX). Fenced code blocks tagged `pseint` render through
 * a read-only CodeMirror view; other fences render as plain `<pre><code>`.
 *
 * HTML entities are decoded at the source-string level so they work inside
 * math nodes too (KaTeX doesn't decode entities itself).
 */
export default function Markdown({ source }: MarkdownProps) {
  const decoded = decodeEntities(source);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className ?? "");
          if (match && match[1] === "pseint") {
            const code = String(children).replace(/\n$/, "");
            return <PseintCodeBlock code={code} />;
          }
          return (
            <code className={className} {...props}>
              {children}
            </code>
          );
        },
      }}
    >
      {decoded}
    </ReactMarkdown>
  );
}