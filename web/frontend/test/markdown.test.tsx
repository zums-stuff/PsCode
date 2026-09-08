/**
 * Markdown renderer tests (plan todo 22 + bug 3 fix).
 *
 * Covers headings, paragraphs, fenced code blocks (rendered via CodeMirror's
 * pseint() mode), inline math (`$x \geq y$` rendered as KaTeX with `≥`),
 * HTML entity handling (decoded at the source-string level so they survive
 * inside math nodes too), and bold/italic/code inline formatting.
 *
 * KaTeX's output DOM includes a `<span class="katex-mathml">` (MathML copy
 * hidden when the browser supports MathML) and a styled HTML copy; the
 * styled HTML copy contains the unicode glyphs (`≥`, `≤`, `≠` ...). We
 * assert against `textContent` of the rendered container — that's what the
 * user sees.
 */

import { describe, expect, it, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import Markdown from "../src/components/Markdown";

beforeEach(() => {
  localStorage.clear();
});

describe("Markdown renderer", () => {
  it("renders headings at the right level", () => {
    const { container } = render(<Markdown source="# Title" />);
    const h1 = container.querySelector("h1");
    expect(h1).not.toBeNull();
    expect(h1).toHaveTextContent("Title");
  });

  it("renders paragraphs and merges consecutive lines into one", () => {
    const { container } = render(
      <Markdown source={"Lee una cadena.\nLa imprime."} />,
    );
    const p = container.querySelectorAll("p");
    expect(p.length).toBeGreaterThan(0);
    const allText = container.textContent ?? "";
    expect(allText).toContain("Lee una cadena.");
    expect(allText).toContain("La imprime.");
  });

  it("renders fenced pseint code blocks via CodeMirror's pseint() mode", () => {
    const { container } = render(
      <Markdown
        source={
          "```pseint\nProceso Suma\n    Leer a, b\n    Escribir a + b\nFinProceso\n```"
        }
      />,
    );
    // CodeMirror renders the doc into a .cm-content; the prose must appear
    // as text content even though the source is split across token spans.
    expect(container.querySelector(".cm-editor")).not.toBeNull();
    expect(container.querySelector(".cm-content")).not.toBeNull();
    const text = container.textContent ?? "";
    expect(text).toContain("Proceso Suma");
    expect(text).toContain("Leer a, b");
    expect(text).toContain("Escribir a + b");
    expect(text).toContain("FinProceso");
  });

  it("renders inline math with KaTeX, producing unicode glyphs", () => {
    const { container } = render(<Markdown source={"$n \\geq 0$"} />);
    // KaTeX wraps math in <span class="katex"> (HTML copy) and emits a
    // parallel MathML copy hidden when MathML is supported. The HTML copy
    // contains the unicode `≥` (U+2265).
    expect(container.querySelector(".katex")).not.toBeNull();
    const text = container.textContent ?? "";
    expect(text).toContain("≥");
  });

  it("renders block math with KaTeX (requires newlines around $$)", () => {
    const { container } = render(
      <Markdown source={"$$\nF(0) = 0, F(1) = 1\n$$"} />,
    );
    expect(container.querySelector(".katex-display")).not.toBeNull();
    const text = container.textContent ?? "";
    expect(text).toContain("0");
    expect(text).toContain("1");
  });

  it("renders the Fibonacci problem statement cleanly", () => {
    const source =
      "Lee un entero $n \\geq 0$ e imprime el $n$-ésimo número de Fibonacci ($F(0)=0$, $F(1)=1$).";
    const { container } = render(<Markdown source={source} />);
    const text = container.textContent ?? "";
    expect(text).not.toContain("&gt;");
    expect(text).not.toContain("&amp;");
    expect(text).not.toContain("&lt;");
    expect(text).toContain("≥");
    expect(text).toContain("Fibonacci");
  });

  it("decodes HTML entities inside math nodes (KaTeX sees `>`, not `&gt;`)", () => {
    // Without pre-decoding, `$n &gt;= 0$` would crash KaTeX (entity not
    // decoded). After decoding, math content is `n >= 0` and KaTeX
    // renders it as `n >= 0` (relation).
    const { container } = render(<Markdown source={"$n &gt;= 0$"} />);
    expect(container.querySelector(".katex-error")).toBeNull();
    expect(container.querySelector(".katex")).not.toBeNull();
    const text = container.textContent ?? "";
    expect(text).not.toContain("&gt;");
    expect(text).toContain(">");
    expect(text).toContain("=");
  });

  it("decodes HTML entities in plain text (no math)", () => {
    const { container } = render(
      <Markdown source={"5 &gt; 3 es verdadero."} />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toContain("&gt;");
    expect(text).toContain("5 > 3");
    expect(text).toContain("verdadero");
  });

  it("does not double-decode escaped entities (`&amp;gt;` stays `&gt;`)", () => {
    const { container } = render(
      <Markdown source={"literal &amp;gt; text"} />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("&gt;");
    expect(text).not.toMatch(/^[^&]*> /);
  });

  it("renders bold, italic, and inline code", () => {
    const { container } = render(
      <Markdown source={"**hola** *mundo* `pseint`"} />,
    );
    const strong = container.querySelector("strong");
    const em = container.querySelector("em");
    const code = container.querySelector("code");
    expect(strong).not.toBeNull();
    expect(strong).toHaveTextContent("hola");
    expect(em).not.toBeNull();
    expect(em).toHaveTextContent("mundo");
    expect(code).not.toBeNull();
    expect(code).toHaveTextContent("pseint");
  });

  it("handles a full user statement with bold/italic/inline code/math/fence", () => {
    const source = [
      "# Suma",
      "",
      "Lee **dos** enteros `a` y `b` y escribe $a + b$.",
      "",
      "```pseint",
      "Proceso Suma",
      "    Leer a, b",
      "    Escribir a + b",
      "FinProceso",
      "```",
    ].join("\n");
    const { container } = render(<Markdown source={source} />);
    const text = container.textContent ?? "";
    expect(container.querySelector("h1")).not.toBeNull();
    expect(container.querySelector("strong")).toHaveTextContent("dos");
    expect(container.querySelector("code")).toHaveTextContent("a");
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector(".cm-content")).not.toBeNull();
    expect(text).toContain("Proceso Suma");
  });
});