import { useEffect, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { pseint } from "@codemirror/lang-pseint";
import { t } from "../lib/i18n";

/** Read-only CodeMirror view of a submission's PseInt source. */
export default function SourceView({ source }: { source: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: source,
        extensions: [
          pseint(),
          EditorView.editable.of(false),
          EditorView.lineWrapping,
        ],
      }),
      parent: container,
    });
    return () => view.destroy();
  }, [source]);

  return (
    <div className="source-view">
      <h4>{t("admin.assignments.source.title")}</h4>
      <div ref={containerRef} />
    </div>
  );
}