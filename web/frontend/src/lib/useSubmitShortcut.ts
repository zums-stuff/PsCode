import { useEffect } from "react";

function isInsideEditor(el: Element | null): boolean {
  if (el === null) return false;
  let current: Element | null = el;
  while (current !== null) {
    if (current.classList?.contains("cm-content")) return true;
    if (current.classList?.contains("cm-editor")) return true;
    current = current.parentElement;
  }
  return false;
}

/**
 * Bind Ctrl+Enter (Cmd+Enter on Mac) to a submit handler at the document
 * level. Only fires when the active element is NOT a <textarea> or an
 * editable CodeMirror instance, so the shortcut never steals keystrokes
 * from the code editor.
 */
export function useSubmitShortcut(onSubmit: () => void): void {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.key !== "Enter") return;
      const target = e.target;
      if (!(target instanceof Element)) return;
      if (target.tagName === "TEXTAREA") return;
      if (isInsideEditor(target)) return;
      e.preventDefault();
      onSubmit();
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onSubmit]);
}
