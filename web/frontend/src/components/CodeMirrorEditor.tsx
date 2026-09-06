import { useEffect, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { basicSetup } from "codemirror";
import { syntaxHighlighting } from "@codemirror/language";
import { linter, lintGutter } from "@codemirror/lint";
import { pseint, pseintHighlightStyle } from "@codemirror/lang-pseint";
import { pseintLinter } from "../lib/linter";

interface CodeMirrorEditorProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Editable CodeMirror 6 wrapper with the pseint mode (todo 28) and the
 * debounced server-side linter (todo 29). Controlled: the parent owns the
 * source string; typing emits onChange, external value changes (reset) are
 * synced back into the view without remounting.
 */
export default function CodeMirrorEditor({ value, onChange }: CodeMirrorEditorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: value,
        extensions: [
          basicSetup,
          pseint(),
          syntaxHighlighting(pseintHighlightStyle),
          keymap.of(defaultKeymap),
          lintGutter(),
          linter(pseintLinter, { delay: 400 }),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              onChangeRef.current(update.state.doc.toString());
            }
          }),
        ],
      }),
      parent: container,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // Mount once; value changes flow through the sync effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (view === null) return;
    const current = view.state.doc.toString();
    if (current !== value) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: value } });
    }
  }, [value]);

  return <div ref={containerRef} className="solve-editor-cm" />;
}