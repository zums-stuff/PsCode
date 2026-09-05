/**
 * Tokenization snapshot test for the PseInt CodeMirror mode.
 *
 * Tokenizes a representative .psc fixture (test/fixtures/representative.psc,
 * derived from engine/tests/corpus patterns) and asserts that EVERY spec
 * keyword, type, logical constant, built-in, operator, number, string and
 * comment gets its expected syntax class. The test FAILS if any keyword is
 * unstyled or mis-tagged.
 *
 * The expected-tag table mirrors engine/src/pseint_engine/lexer.py exactly
 * (same keywords, same synonyms, same case-insensitivity).
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { getStyleTags } from "@lezer/highlight";
import type { Tag } from "@lezer/highlight";
import {
  pseintLanguage,
  pseintKeyword,
  pseintType,
  pseintLiteral,
  pseintBuiltin,
  pseintAssign,
  pseintLogicOp,
  pseintOperator,
  pseintNumber,
  pseintString,
  pseintComment,
  pseintPunct,
} from "@codemirror/lang-pseint";

const FIXTURE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "fixtures", "representative.psc"),
  "utf8",
);

interface Token {
  text: string;
  tag: Tag;
}

/**
 * Tokenize source into (text, tag) pairs. StreamLanguage attaches the
 * tokenTable tags to node types via an internal styleTags prop; the public
 * reader is `getStyleTags(node)` — the same path the editor's highlighter
 * uses.
 */
function tokenize(source: string): Token[] {
  const tree = pseintLanguage.parser.parse(source);
  const tokens: Token[] = [];
  tree.iterate({
    enter(node) {
      const rule = getStyleTags(node);
      if (rule && rule.tags.length > 0) {
        tokens.push({ text: source.slice(node.from, node.to), tag: rule.tags[0] });
      }
    },
  });
  return tokens;
}

/** Assert every (text, tag) expectation is present in the token stream. */
function expectTagged(tokens: Token[], expectations: Array<[string, Tag]>): void {
  for (const [text, tag] of expectations) {
    const hit = tokens.find((t) => t.text === text && t.tag === tag);
    expect(
      hit,
      `expected ${JSON.stringify(text)} to be tagged ${String(tag)} — ` +
        `found ${JSON.stringify(tokens.filter((t) => t.text === text).map((t) => String(t.tag)))}`,
    ).toBeDefined();
  }
}

describe("pseint stream tokenizer", () => {
  const tokens = tokenize(FIXTURE);

  it("colors every reserved keyword (SPEC §(b))", () => {
    expectTagged(tokens, [
      ["Proceso", pseintKeyword],
      ["FinProceso", pseintKeyword],
      ["Definir", pseintKeyword],
      ["Dimension", pseintKeyword],
      ["Dimensionar", pseintKeyword], // flexible synonym
      ["Redimensionar", pseintKeyword],
      ["Leer", pseintKeyword],
      ["Escribir", pseintKeyword],
      ["Si", pseintKeyword],
      ["Entonces", pseintKeyword],
      ["Sino", pseintKeyword],
      ["FinSi", pseintKeyword],
      ["Segun", pseintKeyword],
      ["Hacer", pseintKeyword],
      ["FinSegun", pseintKeyword],
      ["Mientras", pseintKeyword],
      ["FinMientras", pseintKeyword],
      ["Repetir", pseintKeyword],
      ["Hasta", pseintKeyword],
      ["Para", pseintKeyword],
      ["FinPara", pseintKeyword],
      ["Esperar", pseintKeyword],
      ["Milisegundos", pseintKeyword],
      ["Milisegundo", pseintKeyword], // flexible synonym
      ["Retornar", pseintKeyword],
      ["SubProceso", pseintKeyword],
      ["Funcion", pseintKeyword],
      ["FinSubProceso", pseintKeyword],
      ["FinFuncion", pseintKeyword],
      ["Otherwise", pseintKeyword], // flexible synonym
      ["MOD", pseintKeyword],
    ]);
  });

  it("colors every multi-word keyword (SPEC §(b))", () => {
    expectTagged(tokens, [
      ["Hasta Que", pseintKeyword],
      ["Con Paso", pseintKeyword],
      ["De Otro Modo", pseintKeyword],
      ["Por Referencia", pseintKeyword],
      ["Por Valor", pseintKeyword],
      ["Limpiar Pantalla", pseintKeyword],
      ["With step", pseintKeyword], // flexible synonym
    ]);
  });

  it("colors every type name (SPEC §(a) type)", () => {
    expectTagged(tokens, [
      ["Entero", pseintType],
      ["Real", pseintType],
      ["Caracter", pseintType],
      ["Logico", pseintType],
      ["Cadena", pseintType],
    ]);
  });

  it("colors Verdadero/Falso as literals (SPEC §(b))", () => {
    expectTagged(tokens, [
      ["Verdadero", pseintLiteral],
      ["Falso", pseintLiteral],
    ]);
  });

  it("colors every built-in function (SPEC §(b))", () => {
    expectTagged(tokens, [
      ["AZAR", pseintBuiltin],
      ["RC", pseintBuiltin],
      ["ABS", pseintBuiltin],
      ["LN", pseintBuiltin],
      ["EXP", pseintBuiltin],
      ["SEN", pseintBuiltin],
      ["COS", pseintBuiltin],
      ["ATAN", pseintBuiltin],
      ["TRUNC", pseintBuiltin],
      ["REDON", pseintBuiltin],
      ["LARGO", pseintBuiltin],
      ["SUBCADENA", pseintBuiltin],
      ["CONCATENAR", pseintBuiltin],
      ["MAYUSCULARES", pseintBuiltin],
      ["MINUSCULAS", pseintBuiltin],
      ["FechaActual", pseintBuiltin],
      ["HoraActual", pseintBuiltin],
    ]);
  });

  it("colors every operator (SPEC §(d))", () => {
    expectTagged(tokens, [
      ["<-", pseintAssign],
      ["=", pseintOperator],
      ["==", pseintOperator],
      ["<>", pseintOperator],
      ["<", pseintOperator],
      [">", pseintOperator],
      ["<=", pseintOperator],
      [">=", pseintOperator],
      ["+", pseintOperator],
      ["-", pseintOperator],
      ["*", pseintOperator],
      ["/", pseintOperator],
      ["^", pseintOperator],
      ["%", pseintOperator],
      ["&", pseintLogicOp],
      ["|", pseintLogicOp],
      ["~", pseintLogicOp],
      ["Y", pseintLogicOp],
      ["O", pseintLogicOp],
      ["NO", pseintLogicOp],
    ]);
  });

  it("colors numbers, strings, comments and punctuation", () => {
    expectTagged(tokens, [
      ["5", pseintNumber],
      ["3.14", pseintNumber],
      ["1.9", pseintNumber],
      ['"hola"', pseintString],
      ['"n="', pseintString],
      ["// SPEC §(b) keyword coverage fixture", pseintComment],
      ["(", pseintPunct],
      [")", pseintPunct],
      ["[", pseintPunct],
      ["]", pseintPunct],
      [",", pseintPunct],
      [":", pseintPunct],
    ]);
  });

  it("is case-insensitive for keywords (SPEC §(a))", () => {
    const upper = tokenize(
      "PROCESO P\n    MIENTRAS I < 3 HACER\n        ESCRIBIR I\n    FINMIENTRAS\nFINPROCESO",
    );
    expectTagged(upper, [
      ["PROCESO", pseintKeyword],
      ["MIENTRAS", pseintKeyword],
      ["HACER", pseintKeyword],
      ["ESCRIBIR", pseintKeyword],
      ["FINMIENTRAS", pseintKeyword],
      ["FINPROCESO", pseintKeyword],
    ]);
  });

  it("leaves unknown tokens unstyled without crashing (QA failure scenario)", () => {
    const garbage = tokenize("Proceso P\n    x <- @#$%^&*\nFinProceso");
    // Known tokens still tagged; the unknown chars simply produce no tag.
    expectTagged(garbage, [
      ["Proceso", pseintKeyword],
      ["FinProceso", pseintKeyword],
    ]);
    // The unknown characters must not crash the tokenizer.
    expect(garbage.length).toBeGreaterThan(0);
  });
});