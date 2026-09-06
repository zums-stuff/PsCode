/**
 * CodeMirror linter integration for PseInt source (plan todo 29).
 *
 * Wraps POST /api/validate (engine parse, todo 7) and converts the
 * `{ok, errors: [{code, message, line, col}]}` response into CodeMirror
 * `Diagnostic[]`. The 400ms debounce lives in the linter config
 * (`linter(pseintLinter, { delay: 400 })`) — never double-debounce.
 *
 * Position mapping: the engine reports `line` 1-based and `col` 0-based
 * (engine/src/pseint_engine/lexer.py), CodeMirror positions are absolute
 * doc offsets — `from = doc.line(line).from + col`.
 *
 * Network failures return [] (no stale errors) and log a warning; the page
 * may surface a transient notice. No client-side parsing ever happens (M11).
 */

import type { EditorView } from "@codemirror/view";
import type { Diagnostic } from "@codemirror/lint";
import type { Text } from "@codemirror/state";
import { validateSource } from "./api";

/** Engine line (1-based) + col (0-based) -> absolute doc offset. */
export function posFromLineCol(doc: Text, line: number, col: number): number {
  const lineNo = Math.min(Math.max(1, line), doc.lines);
  const lineObj = doc.line(lineNo);
  return Math.min(lineObj.from + Math.max(0, col), lineObj.to);
}

export async function pseintLinter(
  view: EditorView,
): Promise<readonly Diagnostic[]> {
  const source = view.state.doc.toString();
  if (source.trim() === "") return [];

  let result;
  try {
    result = await validateSource(source);
  } catch (err) {
    // Network down / 5xx — drop stale errors, keep the editor usable.
    console.warn("validate request failed", err);
    return [];
  }

  if (result.ok) return [];

  return result.errors.map((e) => {
    const from = posFromLineCol(view.state.doc, e.line, e.col);
    return {
      from,
      to: from + 1,
      severity: "error" as const,
      message: `${e.code} ${e.message}`,
    };
  });
}