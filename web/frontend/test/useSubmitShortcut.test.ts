import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useSubmitShortcut } from "../src/lib/useSubmitShortcut";

describe("useSubmitShortcut", () => {
  it("calls onSubmit when Ctrl+Enter is pressed outside editor/textarea", () => {
    const onSubmit = vi.fn();
    renderHook(() => useSubmitShortcut(onSubmit));

    const input = document.createElement("input");
    document.body.appendChild(input);

    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      ctrlKey: true,
      bubbles: true,
    });
    input.dispatchEvent(event);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    document.body.removeChild(input);
  });

  it("calls onSubmit when Meta+Enter is pressed (Mac)", () => {
    const onSubmit = vi.fn();
    renderHook(() => useSubmitShortcut(onSubmit));

    const div = document.createElement("div");
    document.body.appendChild(div);

    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      metaKey: true,
      bubbles: true,
    });
    div.dispatchEvent(event);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    document.body.removeChild(div);
  });

  it("does NOT fire when focus is inside a textarea", () => {
    const onSubmit = vi.fn();
    renderHook(() => useSubmitShortcut(onSubmit));

    const textarea = document.createElement("textarea");
    document.body.appendChild(textarea);

    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      ctrlKey: true,
      bubbles: true,
    });
    textarea.dispatchEvent(event);

    expect(onSubmit).not.toHaveBeenCalled();
    document.body.removeChild(textarea);
  });

  it("does NOT fire when focus is inside a CodeMirror editor", () => {
    const onSubmit = vi.fn();
    renderHook(() => useSubmitShortcut(onSubmit));

    const cmEditor = document.createElement("div");
    cmEditor.className = "cm-editor";
    const cmContent = document.createElement("div");
    cmContent.className = "cm-content";
    cmEditor.appendChild(cmContent);
    document.body.appendChild(cmEditor);

    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      ctrlKey: true,
      bubbles: true,
    });
    cmContent.dispatchEvent(event);

    expect(onSubmit).not.toHaveBeenCalled();
    document.body.removeChild(cmEditor);
  });

  it("does NOT fire for plain Enter without modifier", () => {
    const onSubmit = vi.fn();
    renderHook(() => useSubmitShortcut(onSubmit));

    const div = document.createElement("div");
    document.body.appendChild(div);

    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
    });
    div.dispatchEvent(event);

    expect(onSubmit).not.toHaveBeenCalled();
    document.body.removeChild(div);
  });

  it("cleans up the listener on unmount", () => {
    const onSubmit = vi.fn();
    const { unmount } = renderHook(() => useSubmitShortcut(onSubmit));
    unmount();

    const div = document.createElement("div");
    document.body.appendChild(div);

    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      ctrlKey: true,
      bubbles: true,
    });
    div.dispatchEvent(event);

    expect(onSubmit).not.toHaveBeenCalled();
    document.body.removeChild(div);
  });
});
