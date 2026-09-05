/**
 * Editor mount test (plan acceptance: "editor mounts in page").
 *
 * A minimal jsdom mount of a CodeMirror EditorView with the pseint()
 * extension — asserts no crash and that syntax classes are present in the
 * rendered DOM. Full Playwright page coverage arrives with Todo 27/29.
 */

import { describe, expect, it } from "vitest";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { pseint } from "@codemirror/lang-pseint";

describe("CodeMirror editor mount with pseint mode", () => {
  it("mounts an EditorView with the pseint extension without crashing", () => {
    const parent = document.createElement("div");
    document.body.appendChild(parent);

    const view = new EditorView({
      state: EditorState.create({
        doc: 'Proceso P\n    Escribir "hola"\nFinProceso',
        extensions: [pseint()],
      }),
      parent,
    });

    expect(parent.querySelector(".cm-editor")).not.toBeNull();
    expect(parent.textContent).toContain("Proceso");
    expect(parent.textContent).toContain("FinProceso");

    // Syntax classes present: highlighted tokens are wrapped in spans.
    const highlighted = parent.querySelectorAll(".cm-line span");
    expect(highlighted.length).toBeGreaterThan(0);

    view.destroy();
    parent.remove();
  });

  it("keeps the editor alive when the document contains unknown tokens", () => {
    const parent = document.createElement("div");
    document.body.appendChild(parent);

    const view = new EditorView({
      state: EditorState.create({
        doc: "Proceso P\n    x <- @#$%^&*\nFinProceso",
        extensions: [pseint()],
      }),
      parent,
    });

    expect(parent.querySelector(".cm-editor")).not.toBeNull();
    expect(parent.textContent).toContain("@#$%^&*");

    view.destroy();
    parent.remove();
  });
});