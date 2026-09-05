/**
 * PseInt language mode for CodeMirror 6.
 *
 * A textmate-style STREAM TOKENIZER ONLY (M11) — no AST/parse logic lives
 * client-side. The engine (engine/src/pseint_engine/lexer.py) does all real
 * parsing server-side; this mode only colors tokens so the editor can
 * highlight PseInt source.
 *
 * The token set mirrors the engine lexer exactly (spec/SPEC.md §(a)/(b)):
 *   - keywords are case-insensitive (matched via lowercase)
 *   - multi-word keywords: "Hasta Que", "Con Paso", "De Otro Modo",
 *     "Por Referencia", "Por Valor", "Limpiar Pantalla" (+ English synonyms)
 *   - flexible synonyms: Dimensionar, Milisegundo, Otherwise, With step
 *   - types: Entero, Real, Caracter, Logico, Cadena
 *   - logical constants: Verdadero, Falso
 *   - built-in functions: AZAR, RC, ABS, LN, EXP, SEN, COS, ATAN, TRUNC,
 *     REDON, LARGO, SUBCADENA, CONCATENAR, MAYUSCULARES, MINUSCULAS,
 *     FechaActual, HoraActual
 *   - operators: <- = == <> < > <= >= + - * / ^ % & | ~ MOD
 *   - numbers: integer / real (no exponent notation)
 *   - strings: double-quoted or single-quoted (engine lexer accepts both)
 *   - comments: // to end of line
 */

import { StreamLanguage, LanguageSupport, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { StreamParser, StringStream } from "@codemirror/language";
import { tags as t, Tag } from "@lezer/highlight";

/* ------------------------------------------------------------------ *
 * Token classes (custom tags so the theme can style each distinctly)
 * ------------------------------------------------------------------ */

/** Reserved keywords: Proceso, FinProceso, Si, Entonces, ... */
export const pseintKeyword = Tag.define("pseintKeyword");
/** Type names: Entero, Real, Caracter, Logico, Cadena */
export const pseintType = Tag.define("pseintType");
/** Logical constants: Verdadero, Falso */
export const pseintLiteral = Tag.define("pseintLiteral");
/** Built-in function names: AZAR, ABS, SUBCADENA, ... */
export const pseintBuiltin = Tag.define("pseintBuiltin");
/** Assignment operator `<-` */
export const pseintAssign = Tag.define("pseintAssign");
/** Logical operators: Y/O/NO words and & | ~ */
export const pseintLogicOp = Tag.define("pseintLogicOp");
/** Arithmetic / relational operators: + - * / ^ % = <> < <= > >= MOD */
export const pseintOperator = Tag.define("pseintOperator");
/** Numbers (integer and real literals) */
export const pseintNumber = Tag.define("pseintNumber");
/** String literals */
export const pseintString = Tag.define("pseintString");
/** Comments (// line) */
export const pseintComment = Tag.define("pseintComment");
/** Punctuation: ( ) [ ] , : */
export const pseintPunct = Tag.define("pseintPunct");

/* ------------------------------------------------------------------ *
 * Keyword tables — mirror engine/src/pseint_engine/lexer.py exactly
 * ------------------------------------------------------------------ */

/** Single-word keywords (lowercase canonical spelling). */
const KEYWORDS = new Set([
  "proceso",
  "finproceso",
  "definir",
  "dimension",
  "dimensionar", // flexible synonym
  "redimensionar",
  "leer",
  "escribir",
  "si",
  "entonces",
  "sino", // covers SiNo and Sino
  "finsi",
  "segun",
  "hacer",
  "finsegun",
  "mientras",
  "finmientras",
  "repetir",
  "hasta",
  "para",
  "finpara",
  "esperar",
  "milisegundos",
  "milisegundo", // flexible synonym
  "retornar",
  "subproceso",
  "funcion",
  "finsubproceso",
  "finfuncion",
  "otherwise", // flexible synonym for De Otro Modo
  "mod",
]);

/** Multi-word keywords (lowercase phrase, words joined by spaces/tabs). */
const MULTIWORD_KEYWORDS: ReadonlyArray<readonly string[]> = [
  ["hasta", "que"],
  ["con", "paso"],
  ["de", "otro", "modo"],
  ["por", "referencia"],
  ["por", "valor"],
  ["limpiar", "pantalla"],
  ["with", "step"], // flexible synonym for Con Paso
];

/** Type names (SPEC §(a) `type`). */
const TYPES = new Set(["entero", "real", "caracter", "logico", "cadena"]);

/** Logical constants (SPEC §(b)). */
const LITERALS = new Set(["verdadero", "falso"]);

/** Built-in functions (SPEC §(b)). */
const BUILTINS = new Set([
  "azar",
  "rc",
  "abs",
  "ln",
  "exp",
  "sen",
  "cos",
  "atan",
  "trunc",
  "redon",
  "largo",
  "subcadena",
  "concatenar",
  "mayusculares",
  "minusculas",
  "fechaactual",
  "horaactual",
]);

/** Word-based logical operators (SPEC §(d) levels 6-7). */
const LOGIC_WORDS = new Set(["y", "o", "no"]);

/* ------------------------------------------------------------------ *
 * Stream parser
 * ------------------------------------------------------------------ */

const IDENT_RE = /^[A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-z0-9_ÁÉÍÓÚÑáéíóúñ]*/;
const NUMBER_RE = /^\d+(\.\d+)?/;
const STRING_RE = /^("([^"\\]|\\.)*"|'([^'\\]|\\.)*')/;
const LINE_COMMENT_RE = /^\/\/.*/;

/**
 * Try to match a multi-word keyword phrase at the stream position.
 * Words are joined by spaces/tabs only (mirrors the engine's
 * `_skip_inline_ws`, which never crosses a newline).
 */
function matchMultiword(stream: StringStream): boolean {
  for (const phrase of MULTIWORD_KEYWORDS) {
    const re = new RegExp("^" + phrase.join("[ \\t]+"), "i");
    if (stream.match(re)) return true;
  }
  return false;
}

const pseintStreamParser: StreamParser<null> = {
  name: "pseint",

  token(stream) {
    if (stream.eatSpace()) return null;
    const ch = stream.peek() ?? "";

    // Line comments: // to end of line (SPEC §(a) comment).
    if (stream.match(LINE_COMMENT_RE)) return "comment";

    // Strings: double- or single-quoted (engine lexer accepts both).
    if (ch === '"' || ch === "'") {
      if (stream.match(STRING_RE)) return "string";
      // Unterminated string: consume to end of line so the rest of the
      // line is not mis-tokenized; the engine reports the CE server-side.
      stream.skipToEnd();
      return "string";
    }

    // Numbers: integer / real, no exponent notation (engine grammar).
    if (/\d/.test(ch)) {
      if (stream.match(NUMBER_RE)) return "number";
    }

    // Words: keywords, types, literals, built-ins, identifiers.
    if (/[A-Za-zÁÉÍÓÚÑáéíóúñ]/.test(ch)) {
      if (matchMultiword(stream)) return "keyword";
      if (stream.match(IDENT_RE)) {
        const word = stream.current().toLowerCase();
        if (KEYWORDS.has(word)) return "keyword";
        if (TYPES.has(word)) return "pseintType";
        if (LITERALS.has(word)) return "literal";
        if (BUILTINS.has(word)) return "pseintBuiltin";
        if (LOGIC_WORDS.has(word)) return "logicOp";
        return "variableName";
      }
    }

    // Two-char operators first (engine lexer order: <- == <> <= >=).
    if (stream.match(/^<-/)) return "assign";
    if (stream.match(/^==/)) return "operator";
    if (stream.match(/^<>/)) return "operator";
    if (stream.match(/^<=/)) return "operator";
    if (stream.match(/^>=/)) return "operator";

    // Single-char operators.
    if (ch === "&" || ch === "|" || ch === "~") {
      stream.next();
      return "logicOp";
    }
    if ("=<>+-*/^%".includes(ch)) {
      stream.next();
      return "operator";
    }
    if ("(),[]:".includes(ch)) {
      stream.next();
      return "punct";
    }

    // Unknown token: consume one char, leave unstyled (page never crashes).
    stream.next();
    return null;
  },

  tokenTable: {
    keyword: pseintKeyword,
    pseintType: pseintType,
    literal: pseintLiteral,
    pseintBuiltin: pseintBuiltin,
    assign: pseintAssign,
    logicOp: pseintLogicOp,
    operator: pseintOperator,
    number: pseintNumber,
    string: pseintString,
    comment: pseintComment,
    punct: pseintPunct,
    variableName: t.variableName,
  },
};

/** The PseInt stream language (highlighting only — no client-side parsing). */
export const pseintLanguage = StreamLanguage.define(pseintStreamParser);

/** Default colors for the PseInt token classes (consumers may override). */
export const pseintHighlightStyle = HighlightStyle.define([
  { tag: pseintKeyword, color: "#7c3aed" },
  { tag: pseintType, color: "#0d9488" },
  { tag: pseintLiteral, color: "#2563eb" },
  { tag: pseintBuiltin, color: "#4f46e5" },
  { tag: pseintAssign, color: "#b91c1c" },
  { tag: pseintLogicOp, color: "#b91c1c" },
  { tag: pseintOperator, color: "#b91c1c" },
  { tag: pseintNumber, color: "#0d9488" },
  { tag: pseintString, color: "#b91c1c" },
  { tag: pseintComment, color: "#78716c" },
  { tag: pseintPunct, color: "#57534e" },
]);

/** LanguageSupport extension: add `pseint()` to a CodeMirror EditorState. */
export function pseint(): LanguageSupport {
  return new LanguageSupport(pseintLanguage, [
    syntaxHighlighting(pseintHighlightStyle),
  ]);
}